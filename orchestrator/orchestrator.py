"""
Orchestrator主模块 - 实现PLAN→ACT→JUDGE状态机
协调Planner、Executor、Judge三个模块的工作
"""
import asyncio
import time
from typing import Dict, Any, Optional, List
from enum import Enum
from datetime import datetime

from schemas.orchestrator import PlannerOutput, JudgeOutput, Plan
from .planner import get_planner
from .executor import get_executor, ExecutionState
from .judge import get_judge
from config import get_config
from telemetry import get_telemetry_logger, TelemetryStage, TelemetryEvent
from .post_mortem_logger import get_post_mortem_logger
from logger import get_logger
from typing import Dict as TypingDict
import uuid

logger = get_logger()


class ActiveTask:
    """活动任务状态"""
    def __init__(self):
        self.plan: Optional[PlannerOutput] = None
        self.execution_state: Optional[ExecutionState] = None
        self.iteration_count: int = 0
        self.plan_iterations: int = 0
        self.total_tool_calls: int = 0
        self.created_at: float = time.time()
        self.last_activity: float = time.time()

    def is_active(self) -> bool:
        """检查任务是否仍然活跃"""
        return self.plan is not None and time.time() - self.last_activity < 3600  # 1小时超时

    def update_activity(self):
        """更新最后活动时间"""
        self.last_activity = time.time()


class PendingAsk:
    """挂起的问题状态"""
    def __init__(self, ask_id: str, question: str, expects: str):
        self.ask_id = ask_id
        self.question = question
        self.expects = expects  # 期望的答案类型，如 "city|date|..."
        self.ts = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ask_id": self.ask_id,
            "question": self.question,
            "expects": self.expects,
            "ts": self.ts
        }


class SessionState:
    """会话状态"""
    def __init__(self):
        self.active_task: Optional[ActiveTask] = None
        self.pending_ask: Optional[PendingAsk] = None
        self.session_id: str = str(uuid.uuid4())
        self.created_at: float = time.time()

    def has_pending_ask(self) -> bool:
        """检查是否有挂起的问题"""
        return self.pending_ask is not None

    def set_pending_ask(self, question: str, expects: str):
        """设置挂起的问题"""
        ask_id = str(uuid.uuid4())
        self.pending_ask = PendingAsk(ask_id, question, expects)
        logger.info(f"设置挂起问题: {question} (期望: {expects})")

    def clear_pending_ask(self):
        """清除挂起的问题"""
        if self.pending_ask:
            logger.info(f"清除挂起问题: {self.pending_ask.question}")
            self.pending_ask = None

    def start_new_task(self):
        """开始新任务"""
        self.active_task = ActiveTask()
        self.clear_pending_ask()
        logger.info("开始新任务")

    def end_task(self):
        """结束当前任务"""
        if self.active_task:
            logger.info("结束当前任务")
        self.active_task = None
        self.clear_pending_ask()


# 全局会话存储
_sessions: TypingDict[str, SessionState] = {}


def get_session(session_id: str) -> SessionState:
    """获取或创建会话"""
    if session_id not in _sessions:
        _sessions[session_id] = SessionState()
        _sessions[session_id].session_id = session_id
        logger.info(f"创建新会话: {session_id}")
    return _sessions[session_id]


def cleanup_old_sessions():
    """清理过期的会话（可选，后台任务）"""
    current_time = time.time()
    expired_sessions = [
        sid for sid, session in _sessions.items()
        if current_time - session.created_at > 86400  # 24小时
    ]
    for sid in expired_sessions:
        del _sessions[sid]
        logger.info(f"清理过期会话: {sid}")


class OrchestratorState(Enum):
    """编排器状态"""
    PLAN = "plan"
    ACT = "act"
    JUDGE = "judge"
    ASK_USER = "ask_user"
    DONE = "done"
    FAILED = "failed"


class OrchestratorResult:
    """编排器执行结果"""

    def __init__(self):
        self.final_plan: Optional[PlannerOutput] = None
        self.execution_state: Optional[ExecutionState] = None
        self.judge_history: List[JudgeOutput] = []
        self.iteration_count: int = 0
        self.plan_iterations: int = 0
        self.total_tool_calls: int = 0
        self.total_time: float = 0.0
        self.status: str = "pending"
        self.error_message: Optional[str] = None
        self.final_answer: Optional[str] = None
        self.pending_questions: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "final_plan": self.final_plan.dict() if self.final_plan else None,
            "execution_state": {
                "artifacts": self.execution_state.artifacts if self.execution_state else {},
                "errors": self.execution_state.errors if self.execution_state else [],
                "completed_steps": self.execution_state.completed_steps if self.execution_state else []
            } if self.execution_state else None,
            "judge_history": [jr.dict() for jr in self.judge_history],
            "iteration_count": self.iteration_count,
            "plan_iterations": self.plan_iterations,
            "total_tool_calls": self.total_tool_calls,
            "total_time": self.total_time,
            "status": self.status,
            "error_message": self.error_message,
            "final_answer": self.final_answer,
            "pending_questions": self.pending_questions
        }


class Orchestrator:
    """编排器主类"""

    def __init__(self):
        """初始化编排器"""
        config = get_config()

        # 预算控制参数
        self.max_plan_iters = config.max_plan_iters  # 最大规划迭代次数
        self.max_tool_calls_per_act = config.max_tool_calls_per_act  # 单次ACT最大工具调用数
        self.max_total_tool_calls = config.max_total_tool_calls  # 总工具调用数上限
        self.max_execution_time = config.max_latency_ms / 1000.0  # 最大执行时间（秒）

        # 获取各模块实例
        self.planner = get_planner()
        self.executor = get_executor()
        self.judge = get_judge()
        self.post_mortem_logger = get_post_mortem_logger()
        self.telemetry = get_telemetry_logger()

        logger.info(f"编排器初始化完成: max_plan_iters={self.max_plan_iters}, max_total_tool_calls={self.max_total_tool_calls}")

    async def process_message(self, user_query: str, session_id: str, context: Dict[str, Any] = None) -> OrchestratorResult:
        """
        处理用户消息 - 主入口，支持会话状态管理

        Args:
            user_query: 用户查询
            session_id: 会话ID
            context: 上下文信息

        Returns:
            处理结果
        """
        session = get_session(session_id)

        # 判断是继续任务还是新任务
        if session.has_pending_ask():
            # 有挂起的问题，这是继续任务
            return await self._resume_with_answer(user_query, session)
        else:
            # 检查是否有活跃任务且用户要开始新任务（这会忽略挂起的问题）
            if session.active_task and session.active_task.is_active() and self._is_new_task_request(user_query):
                # Telemetry: 用户忽略了活跃任务，开始新任务
                self.telemetry.log_event(
                    stage=TelemetryStage.ASK_USER,
                    event=TelemetryEvent.ASK_USER_IGNORED,
                    user_query=user_query,
                    context={
                        "reason": "new_task_requested_with_active_task",
                        "had_active_task": True,
                        "task_age_seconds": time.time() - session.active_task.created_at
                    }
                )
                session.end_task()  # 结束旧任务

            # 检查是否有活跃任务
            if session.active_task and session.active_task.is_active():
                # 继续现有任务
                return await self._continue_task(user_query, session)
            else:
                # 开始新任务
                return await self._start_new_task(user_query, session, context)

    def _is_new_task_request(self, user_query: str) -> bool:
        """检查是否是新任务请求"""
        new_task_keywords = [
            "新的问题", "new question", "reset", "重来", "重新开始",
            "新任务", "new task", "clear", "清除"
        ]
        query_lower = user_query.lower().strip()
        return any(keyword in query_lower for keyword in new_task_keywords)

    def _is_task_termination(self, user_query: str) -> bool:
        """检查是否是任务终止请求"""
        termination_keywords = [
            "结束", "结束任务", "拜拜", "再见", "结束对话", "停止",
            "end", "bye", "goodbye", "stop", "quit"
        ]
        query_lower = user_query.lower().strip()
        return any(keyword in query_lower for keyword in termination_keywords)

    async def _start_new_task(self, user_query: str, session: SessionState, context: Dict[str, Any] = None) -> OrchestratorResult:
        """开始新任务"""
        session.start_new_task()
        return await self.orchestrate(user_query, context, session.active_task)

    async def _continue_task(self, user_query: str, session: SessionState) -> OrchestratorResult:
        """继续现有任务"""
        if not session.active_task:
            # 不应该发生的情况
            return await self._start_new_task(user_query, session)

        # 检查是否是任务终止
        if self._is_task_termination(user_query):
            session.end_task()
            result = OrchestratorResult()
            result.status = "terminated"
            result.final_answer = "任务已结束。如有其他问题，请随时询问！"
            return result

        # 继续现有任务
        session.active_task.update_activity()
        return await self.orchestrate(user_query, None, session.active_task)

    async def _resume_with_answer(self, user_answer: str, session: SessionState) -> OrchestratorResult:
        """使用用户答案恢复任务"""
        if not session.pending_ask or not session.active_task:
            # 不应该发生的情况
            session.clear_pending_ask()
            return self._start_new_task(user_answer, session)

        # 记录用户答案
        pending_ask = session.pending_ask
        logger.info(f"收到用户答案: {user_answer} (针对问题: {pending_ask.question})")

        # 清除挂起状态
        session.clear_pending_ask()

        # 将答案填入execution state
        if not session.active_task.execution_state:
            session.active_task.execution_state = ExecutionState()

        # 根据期望的答案类型设置参数
        if "city" in pending_ask.expects.lower():
            session.active_task.execution_state.set_artifact("user_city", user_answer)
        elif "date" in pending_ask.expects.lower():
            session.active_task.execution_state.set_artifact("user_date", user_answer)
        else:
            session.active_task.execution_state.set_artifact("user_answer", user_answer)

        # 强制重新规划
        return self._force_replan(session.active_task)

    async def _force_replan(self, active_task: ActiveTask) -> OrchestratorResult:
        """强制重新规划当前任务"""
        if not active_task or not active_task.execution_state:
            # 创建新的编排结果
            result = OrchestratorResult()
            result.status = "error"
            result.error_message = "无法重新规划：缺少任务状态"
            return result

        try:
            # 使用execution state中的信息重新规划
            # 构建包含用户回答的上下文
            user_city = active_task.execution_state.get_artifact("user_city")
            user_date = active_task.execution_state.get_artifact("user_date")
            user_answer = active_task.execution_state.get_artifact("user_answer")

            # 构建增强的上下文
            enhanced_context = {}
            if user_city:
                enhanced_context["user_city"] = user_city
            if user_date:
                enhanced_context["user_date"] = user_date
            if user_answer:
                enhanced_context["user_answer"] = user_answer

            # 创建一个描述性的查询，包含用户提供的信息
            context_parts = []
            if user_city:
                context_parts.append(f"城市: {user_city}")
            if user_date:
                context_parts.append(f"日期: {user_date}")
            if user_answer:
                context_parts.append(f"用户回答: {user_answer}")

            replan_query = f"继续执行任务。用户提供的信息: {'; '.join(context_parts)}"

            # 重新规划并执行
            return await self.orchestrate(replan_query, enhanced_context, active_task)

        except Exception as e:
            logger.error(f"强制重新规划失败: {e}")

            # Telemetry: 记录REPLAN失败
            self.telemetry.log_event(
                stage=TelemetryStage.ASK_USER,
                event=TelemetryEvent.PLANNER_NON_JSON,  # 复用这个事件类型
                user_query="replan_after_user_answer",
                context={"error": str(e), "stage": "force_replan"}
            )

            # 返回错误结果
            result = OrchestratorResult()
            result.status = "error"
            result.error_message = f"重新规划失败: {str(e)}"
            return result

    async def orchestrate(self, user_query: str, context: Dict[str, Any] = None, active_task: ActiveTask = None) -> OrchestratorResult:
        """
        执行完整的编排流程

        Args:
            user_query: 用户查询
            context: 上下文信息
            active_task: 现有活动任务（可选）

        Returns:
            OrchestratorResult: 执行结果
        """
        result = OrchestratorResult()
        start_time = time.time()

        # 使用现有任务或创建新结果
        if active_task:
            # 从现有任务恢复状态
            result.final_plan = active_task.plan
            result.execution_state = active_task.execution_state
            result.iteration_count = active_task.iteration_count
            result.plan_iterations = active_task.plan_iterations
            result.total_tool_calls = active_task.total_tool_calls

        # 开始备现身复盘会话
        session_id = f"session_{int(time.time())}_{hash(user_query) % 10000}"
        self.post_mortem_logger.start_session(session_id, user_query, "m3")

        try:
            logger.info(f"开始编排用户查询: {user_query[:100]}{'...' if len(user_query) > 100 else ''}")

            current_state = OrchestratorState.PLAN
            plan_iter = 0  # 规划迭代次数

            while current_state not in [OrchestratorState.DONE, OrchestratorState.FAILED]:

                logger.info(f"当前状态: {current_state.value}, 规划轮次: {plan_iter}, 总工具调用: {result.total_tool_calls}")

                # 检查预算
                elapsed_time = time.time() - start_time
                if elapsed_time > self.max_execution_time:
                    logger.warning(f"超过最大执行时间 {self.max_execution_time}s")
                    current_state = OrchestratorState.FAILED
                    result.error_message = f"超过最大执行时间 ({self.max_execution_time}s)"
                    break

                if result.total_tool_calls >= self.max_total_tool_calls:
                    logger.warning(f"达到总工具调用上限 {self.max_total_tool_calls}")

                    # Telemetry: 预算超限
                    self.telemetry.log_event(
                        stage=TelemetryStage.ACT,
                        event=TelemetryEvent.BUDGET_EXCEEDED,
                        user_query=user_query,
                        context={"reason": "total_tool_calls_exceeded", "current": result.total_tool_calls, "limit": self.max_total_tool_calls},
                        limits={"tool_calls_used": result.total_tool_calls, "budget": {"max_calls": self.max_total_tool_calls}}
                    )

                    current_state = OrchestratorState.FAILED
                    result.error_message = f"达到总工具调用上限 ({self.max_total_tool_calls})"
                    break

                if plan_iter >= self.max_plan_iters:
                    logger.warning(f"达到最大规划迭代次数 {self.max_plan_iters}")

                    # Telemetry: JUDGE_LOOP - 反复REPLAN超阈值
                    self.telemetry.log_event(
                        stage=TelemetryStage.JUDGE,
                        event=TelemetryEvent.JUDGE_LOOP,
                        user_query=user_query,
                        context={"reason": "max_plan_iterations_exceeded", "iterations": plan_iter, "limit": self.max_plan_iters},
                        plan_excerpt={"iterations": plan_iter}
                    )

                    current_state = OrchestratorState.FAILED
                    result.error_message = f"达到最大规划迭代次数 ({self.max_plan_iters})"
                    break

                # 状态机逻辑
                if current_state == OrchestratorState.PLAN:
                    plan_iter += 1
                    result.plan_iterations = plan_iter
                    self.post_mortem_logger.log_phase_start("PLAN", plan_iter)
                    current_state = await self._plan_phase(user_query, context, result)

                elif current_state == OrchestratorState.ACT:
                    self.post_mortem_logger.log_phase_start("ACT", plan_iter)
                    current_state = await self._act_phase(result.final_plan, result)

                elif current_state == OrchestratorState.JUDGE:
                    self.post_mortem_logger.log_phase_start("JUDGE", plan_iter)
                    current_state = await self._judge_phase(result.final_plan, result.execution_state, result)

                elif current_state == OrchestratorState.ASK_USER:
                    # ASK_USER状态：设置pending_ask并等待用户输入
                    logger.info("设置pending_ask状态，等待用户回答问题")
                    result.status = "waiting_for_user"
                    # pending_ask会在UI层通过session状态管理
                    break

                self.post_mortem_logger.log_phase_end(current_state.value, "completed")

            # 设置最终状态
            result.status = current_state.value
            result.iteration_count = plan_iter

            # 生成最终答案
            if current_state == OrchestratorState.DONE and result.final_plan and result.execution_state:
                result.final_answer = self._generate_final_answer(result.final_plan, result.execution_state)

            logger.info(f"编排完成: 状态={result.status}, 规划轮次={plan_iter}, 总工具调用={result.total_tool_calls}")

        except Exception as e:
            logger.error(f"编排过程出错: {e}", exc_info=True)
            result.status = OrchestratorState.FAILED.value
            result.error_message = str(e)

        finally:
            result.total_time = time.time() - start_time

            # 结束备现身复盘会话
            final_result = {
                "status": result.status,
                "iteration_count": result.iteration_count,
                "total_time": result.total_time,
                "error_message": result.error_message,
                "plan_steps": len(result.final_plan.steps) if result.final_plan else 0,
                "tool_calls": len(result.execution_state.artifacts) if result.execution_state else 0
            }
            self.post_mortem_logger.end_session(final_result, result.error_message)

        return result

    async def continue_with_user_answer(self, user_answer: str, result: OrchestratorResult) -> OrchestratorResult:
        """
        处理用户回答并继续执行

        根据新状态机逻辑：
        1. 写入用户回答到execution state
        2. 强制调用Planner重新规划
        3. 继续执行ACT阶段
        """
        try:
            if not result.execution_state:
                raise ValueError("没有执行状态，无法处理用户回答")

            # 写入用户回答到execution state
            result.execution_state.set_artifact("user_answer", user_answer)
            logger.info(f"用户已回答问题: {user_answer}")

            # 清除pending问题状态
            result.pending_questions = []

            # 从ASK_USER状态开始，重新进入PLAN状态
            current_state = OrchestratorState.PLAN
            start_time = time.time()

            # 继续状态机循环
            while current_state not in [OrchestratorState.DONE, OrchestratorState.FAILED]:

                # 检查预算
                elapsed_time = time.time() - start_time
                if elapsed_time > self.max_execution_time:
                    current_state = OrchestratorState.FAILED
                    result.error_message = f"继续执行超时 ({self.max_execution_time}s)"
                    break

                if result.total_tool_calls >= self.max_total_tool_calls:
                    current_state = OrchestratorState.FAILED
                    result.error_message = f"达到总工具调用上限 ({self.max_total_tool_calls})"
                    break

                # 状态机逻辑（从PLAN开始）
                if current_state == OrchestratorState.PLAN:
                    result.plan_iterations += 1
                    self.post_mortem_logger.log_phase_start("PLAN", result.plan_iterations)
                    current_state = await self._plan_phase("", {}, result)  # 使用空的query，因为已经有execution state

                elif current_state == OrchestratorState.ACT:
                    self.post_mortem_logger.log_phase_start("ACT", result.plan_iterations)
                    current_state = await self._act_phase(result.final_plan, result)

                elif current_state == OrchestratorState.JUDGE:
                    self.post_mortem_logger.log_phase_start("JUDGE", result.plan_iterations)
                    current_state = await self._judge_phase(result.final_plan, result.execution_state, result)

                self.post_mortem_logger.log_phase_end(current_state.value, "completed")

            # 更新最终状态
            result.status = current_state.value
            result.total_time += time.time() - start_time

            # 生成最终答案
            if current_state == OrchestratorState.DONE and result.final_plan and result.execution_state:
                result.final_answer = self._generate_final_answer(result.final_plan, result.execution_state)

            logger.info(f"继续执行完成: 状态={result.status}")
            return result

        except Exception as e:
            logger.error(f"处理用户回答失败: {e}")
            result.status = OrchestratorState.FAILED.value
            result.error_message = f"处理用户回答失败: {e}"
            return result

    def _create_remaining_plan(self, original_plan: PlannerOutput, execution_state: ExecutionState) -> PlannerOutput:
        """创建剩余步骤的计划"""
        # 找到已完成的步骤
        completed_steps = set(execution_state.completed_steps)

        # 过滤出未完成的步骤
        remaining_steps = [
            step for step in original_plan.steps
            if step.id not in completed_steps
        ]

        # 创建新计划
        remaining_plan = Plan(
            goal=f"继续执行: {original_plan.goal}",
            success_criteria=original_plan.success_criteria,
            max_steps=len(remaining_steps),
            steps=remaining_steps,
            final_answer_template=original_plan.final_answer_template
        )

        return remaining_plan

    async def _plan_phase(self, user_query: str, context: Dict[str, Any],
                         result: OrchestratorResult) -> OrchestratorState:
        """规划阶段"""
        try:
            logger.info(f"规划阶段 (第{result.plan_iterations}轮)")

            # 创建计划
            plan = await self.planner.create_plan(user_query, context)
            result.final_plan = plan

            logger.info(f"规划完成: {len(plan.steps)} 个步骤")
            return OrchestratorState.ACT

        except Exception as e:
            logger.error(f"规划阶段失败: {e}")
            return OrchestratorState.FAILED

    async def _act_phase(self, plan: PlannerOutput, result: OrchestratorResult) -> OrchestratorState:
        """执行阶段"""
        try:
            logger.info(f"执行阶段 (第{result.plan_iterations}轮)")

            # 执行计划，考虑预算限制
            execution_state = await self.executor.execute_plan(plan, max_tool_calls=self.max_tool_calls_per_act)

            result.execution_state = execution_state
            result.total_tool_calls += len(execution_state.completed_steps)

            logger.info(f"执行完成: {len(execution_state.completed_steps)}/{len(plan.steps)} 步骤成功")

            # 检查是否有等待用户输入的步骤（通过ask_user工具）
            ask_user_pending = execution_state.get_artifact("ask_user_pending")
            if ask_user_pending:
                result.pending_questions = ask_user_pending.get("questions", [])
                logger.info(f"执行阶段暂停，等待用户回答问题")
                return OrchestratorState.ASK_USER

            # 如果有执行错误，记录但继续判断
            if execution_state.errors:
                logger.warning(f"执行过程中有 {len(execution_state.errors)} 个错误")

            return OrchestratorState.JUDGE

        except Exception as e:
            logger.error(f"执行阶段失败: {e}")
            return OrchestratorState.FAILED

    async def _judge_phase(self, plan: PlannerOutput, execution_state: ExecutionState,
                          result: OrchestratorResult) -> OrchestratorState:
        """判断阶段"""
        try:
            logger.info(f"判断阶段 (第{result.plan_iterations}轮)")

            # 评估执行结果
            judge_result = await self.judge.evaluate_execution(plan, execution_state, result.plan_iterations)

            result.judge_history.append(judge_result)

            logger.info(f"判断结果: satisfied={judge_result.satisfied}")

            # 根据判断结果决定下一步
            if judge_result.satisfied:
                # 满足条件，执行完成
                return OrchestratorState.DONE
            elif judge_result.questions:
                # 需要向用户提问
                result.pending_questions = judge_result.questions
                logger.info(f"需要向用户提问: {judge_result.questions}")
                return OrchestratorState.ASK_USER
            else:
                # 需要重新规划
                logger.info("需要重新规划")
                return OrchestratorState.PLAN

        except Exception as e:
            logger.error(f"判断阶段失败: {e}")
            return OrchestratorState.FAILED

    def _generate_final_answer(self, plan: Plan, execution_state: ExecutionState) -> str:
        """生成最终答案"""
        try:
            template = plan.final_answer_template

            # 替换模板中的变量
            for key, value in execution_state.artifacts.items():
                placeholder = "{{" + key + "}}"
                if placeholder in template:
                    if isinstance(value, (dict, list)):
                        # 对于复杂对象，使用格式化的字符串
                        import json
                        value_str = json.dumps(value, ensure_ascii=False, indent=2)
                    else:
                        value_str = str(value)
                    template = template.replace(placeholder, value_str)

            return template

        except Exception as e:
            logger.error(f"生成最终答案失败: {e}")
            return "抱歉，生成答案时出现错误。"

    async def orchestrate_with_callback(self,
                                      user_query: str,
                                      context: Dict[str, Any] = None,
                                      callback: callable = None) -> OrchestratorResult:
        """
        带回调的编排执行（用于实时状态更新）

        Args:
            user_query: 用户查询
            context: 上下文信息
            callback: 状态回调函数
        """
        if callback:
            # 可以在这里添加状态回调逻辑
            pass

        return await self.orchestrate(user_query, context)


# 全局编排器实例
_orchestrator_instance = None


def get_orchestrator() -> Orchestrator:
    """获取编排器实例"""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = Orchestrator()
    return _orchestrator_instance


async def orchestrate_query(user_query: str,
                          context: Dict[str, Any] = None) -> OrchestratorResult:
    """
    编排用户查询的便捷函数

    Args:
        user_query: 用户查询
        context: 上下文信息

    Returns:
        OrchestratorResult: 执行结果
    """
    orchestrator = get_orchestrator()
    return await orchestrator.orchestrate(user_query, context)


if __name__ == "__main__":
    # 测试编排器
    async def test_orchestrator():
        orchestrator = Orchestrator(max_iterations=1)  # 限制为1轮便于测试

        test_query = "现在几点了？今天是星期几？"

        try:
            result = await orchestrator.orchestrate(test_query)
            print("✅ 编排成功:")
            print(f"状态: {result.status}")
            print(f"迭代次数: {result.iteration_count}")
            print(f"总时间: {result.total_time:.2f}s")

            if result.final_answer:
                print(f"最终答案: {result.final_answer}")

            if result.execution_state:
                print(f"执行产出: {len(result.execution_state.artifacts)} 个")
                for key, value in result.execution_state.artifacts.items():
                    print(f"  {key}: {str(value)[:50]}...")

        except Exception as e:
            print(f"❌ 编排失败: {e}")

    asyncio.run(test_orchestrator())
