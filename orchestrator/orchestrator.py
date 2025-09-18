"""
Orchestrator主模块 - 实现PLAN→ACT→JUDGE状态机
协调Planner、Executor、Judge三个模块的工作
"""
import asyncio
import time
from typing import Dict, Any, Optional, List
from enum import Enum
from datetime import datetime

from schemas.plan import Plan, PlanStep, StepType
from .planner import get_planner
from .executor import get_executor, ExecutionState, AskUserException
from .judge import get_judge, JudgeResult
from .post_mortem_logger import get_post_mortem_logger
from logger import get_logger

logger = get_logger()


class OrchestratorState(Enum):
    """编排器状态"""
    PLAN = "plan"
    ACT = "act"
    ASK_USER = "ask_user"
    JUDGE = "judge"
    DONE = "done"
    FAILED = "failed"


class OrchestratorResult:
    """编排器执行结果"""

    def __init__(self):
        self.final_plan: Optional[Plan] = None
        self.execution_state: Optional[ExecutionState] = None
        self.judge_history: List[JudgeResult] = []
        self.iteration_count: int = 0
        self.total_time: float = 0.0
        self.status: str = "pending"
        self.error_message: Optional[str] = None
        self.final_answer: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "final_plan": self.final_plan.dict() if self.final_plan else None,
            "execution_state": {
                "artifacts": self.execution_state.artifacts if self.execution_state else {},
                "errors": self.execution_state.errors if self.execution_state else [],
                "completed_steps": self.execution_state.completed_steps if self.execution_state else []
            } if self.execution_state else None,
            "judge_history": [jr.to_dict() for jr in self.judge_history],
            "iteration_count": self.iteration_count,
            "total_time": self.total_time,
            "status": self.status,
            "error_message": self.error_message,
            "final_answer": self.final_answer
        }


class Orchestrator:
    """编排器主类"""

    def __init__(self, max_iterations: int = 2, max_execution_time: float = 60.0):
        """
        初始化编排器

        Args:
            max_iterations: 最大迭代次数
            max_execution_time: 最大执行时间（秒）
        """
        self.max_iterations = max_iterations
        self.max_execution_time = max_execution_time

        # 获取各模块实例
        self.planner = get_planner()
        self.executor = get_executor()
        self.judge = get_judge()
        self.post_mortem_logger = get_post_mortem_logger()

        logger.info(f"编排器初始化完成: max_iterations={max_iterations}, max_time={max_execution_time}s")

    async def orchestrate(self, user_query: str, context: Dict[str, Any] = None) -> OrchestratorResult:
        """
        执行完整的编排流程

        Args:
            user_query: 用户查询
            context: 上下文信息

        Returns:
            OrchestratorResult: 执行结果
        """
        result = OrchestratorResult()
        start_time = time.time()

        # 开始备现身复盘会话
        session_id = f"session_{int(time.time())}_{hash(user_query) % 10000}"
        self.post_mortem_logger.start_session(session_id, user_query, "m3")

        try:
            logger.info(f"开始编排用户查询: {user_query[:100]}{'...' if len(user_query) > 100 else ''}")

            current_state = OrchestratorState.PLAN
            iteration = 1

            while current_state != OrchestratorState.DONE and current_state != OrchestratorState.FAILED:

                logger.info(f"当前状态: {current_state.value}, 迭代轮次: {iteration}")

                # 检查是否超过最大执行时间（在每次迭代开始时检查）
                elapsed_time = time.time() - start_time
                if elapsed_time > self.max_execution_time:
                    logger.warning(f"超过最大执行时间 {self.max_execution_time}s，停止执行")
                    current_state = OrchestratorState.FAILED
                    result.error_message = f"超过最大执行时间 ({self.max_execution_time}s)"
                    break

                if current_state == OrchestratorState.PLAN:
                    self.post_mortem_logger.log_phase_start("PLAN", iteration)
                    current_state, plan = await self._plan_phase(user_query, context, iteration, result)
                    self.post_mortem_logger.log_phase_end("PLAN", "completed" if current_state != OrchestratorState.FAILED else "failed")

                elif current_state == OrchestratorState.ACT:
                    self.post_mortem_logger.log_phase_start("ACT", iteration)
                    current_state, execution_state = await self._act_phase(result.final_plan, iteration, result)
                    status = "completed"
                    if current_state == OrchestratorState.ASK_USER:
                        status = "waiting_user_input"
                    elif current_state == OrchestratorState.FAILED:
                        status = "failed"
                    self.post_mortem_logger.log_phase_end("ACT", status)

                elif current_state == OrchestratorState.ASK_USER:
                    # 用户询问状态，等待用户输入后再继续
                    logger.info("编排器进入用户询问等待状态")
                    # 记录用户交互等待状态
                    ask_user_data = result.execution_state.get_artifact("ask_user_pending") if result.execution_state else None
                    if ask_user_data:
                        self.post_mortem_logger.log_user_interaction("waiting_for_user", ask_user_data["question"])
                    current_state = OrchestratorState.ASK_USER  # 保持在ASK_USER状态，等待外部输入

                elif current_state == OrchestratorState.JUDGE:
                    self.post_mortem_logger.log_phase_start("JUDGE", iteration)
                    current_state, judge_result = await self._judge_phase(result.final_plan, result.execution_state, iteration, result)
                    self.post_mortem_logger.log_phase_end("JUDGE", "completed" if current_state == OrchestratorState.DONE else "failed")

                # 只有在需要重新规划时才增加迭代次数
                if current_state == OrchestratorState.PLAN and iteration > 1:
                    iteration += 1

                    # 检查是否超过最大迭代次数（只在重新规划时检查）
                    if iteration > self.max_iterations:
                        logger.warning(f"达到最大迭代次数 {self.max_iterations}，停止执行")
                        current_state = OrchestratorState.FAILED
                        result.error_message = f"超过最大迭代次数 ({self.max_iterations})"
                        break

            # 设置最终状态
            result.status = current_state.value
            result.iteration_count = iteration - 1

            # 生成最终答案
            if current_state == OrchestratorState.DONE and result.final_plan and result.execution_state:
                result.final_answer = self._generate_final_answer(result.final_plan, result.execution_state)

            logger.info(f"编排完成: 状态={result.status}, 迭代次数={result.iteration_count}")

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
        """处理用户回答并继续执行"""
        try:
            if not result.execution_state:
                raise ValueError("没有执行状态，无法处理用户回答")

            ask_user_data = result.execution_state.get_artifact("ask_user_pending")
            if not ask_user_data:
                raise ValueError("没有等待的用户问题")

            # 保存用户回答
            result.execution_state.set_artifact(ask_user_data["output_key"], user_answer)
            result.execution_state.set_artifact(f"ask_user_{ask_user_data['step_id']}_answered", {
                **ask_user_data,
                "answer": user_answer,
                "status": "answered"
            })

            logger.info(f"用户已回答问题: {ask_user_data['question']} -> {user_answer}")

            # 继续执行剩余步骤
            remaining_plan = self._create_remaining_plan(result.final_plan, result.execution_state)
            if remaining_plan.steps:
                logger.info(f"继续执行剩余 {len(remaining_plan.steps)} 个步骤")
                await self.executor.execute_plan(remaining_plan, result.execution_state)
            else:
                logger.info("所有步骤已完成")

            # 继续判断阶段
            judge_result = await self.judge.evaluate_execution(result.final_plan, result.execution_state, 1)
            result.judge_history.append(judge_result)

            if judge_result.satisfied:
                result.status = OrchestratorState.DONE.value
            else:
                result.status = OrchestratorState.FAILED.value

            return result

        except Exception as e:
            logger.error(f"处理用户回答失败: {e}")
            result.status = OrchestratorState.FAILED.value
            result.error_message = f"处理用户回答失败: {e}"
            return result

    def _create_remaining_plan(self, original_plan: Plan, execution_state: ExecutionState) -> Plan:
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
                         iteration: int, result: OrchestratorResult) -> tuple:
        """规划阶段"""
        try:
            logger.info(f"规划阶段 (第{iteration}轮)")

            # 如果是第一轮，直接规划
            if iteration == 1:
                plan = await self.planner.create_plan(user_query, context)
            else:
                # 后续轮次基于之前的判断结果调整计划
                last_judge = result.judge_history[-1] if result.judge_history else None
                if last_judge and last_judge.plan_patch:
                    # 这里应该合并plan_patch，但现在简化处理
                    logger.info("检测到计划补丁，但暂时使用原计划")
                    plan = result.final_plan
                else:
                    plan = result.final_plan

            result.final_plan = plan
            logger.info(f"规划完成: {len(plan.steps)} 个步骤")

            return OrchestratorState.ACT, plan

        except Exception as e:
            logger.error(f"规划阶段失败: {e}")
            return OrchestratorState.FAILED, None

    async def _act_phase(self, plan: Plan, iteration: int, result: OrchestratorResult) -> tuple:
        """执行阶段"""
        try:
            logger.info(f"执行阶段 (第{iteration}轮)")

            # 执行计划
            execution_state = await self.executor.execute_plan(plan)

            result.execution_state = execution_state
            logger.info(f"执行完成: {len(execution_state.completed_steps)}/{len(plan.steps)} 步骤成功")

            # 检查是否有等待用户输入的步骤
            if execution_state.get_artifact("ask_user_pending"):
                ask_user_data = execution_state.get_artifact("ask_user_pending")
                logger.info(f"执行阶段暂停，等待用户回答: {ask_user_data['question']}")
                return OrchestratorState.ASK_USER, execution_state

            # 如果有执行错误，记录但继续判断
            if execution_state.errors:
                logger.warning(f"执行过程中有 {len(execution_state.errors)} 个错误")

            return OrchestratorState.JUDGE, execution_state

        except AskUserException as e:
            # 直接处理用户询问异常
            logger.info(f"执行阶段遇到用户询问: {e.ask_user_data['question']}")
            result.execution_state = ExecutionState()
            result.execution_state.set_artifact("ask_user_pending", e.ask_user_data)
            return OrchestratorState.ASK_USER, result.execution_state

        except Exception as e:
            logger.error(f"执行阶段失败: {e}")
            return OrchestratorState.FAILED, None

    async def _judge_phase(self, plan: Plan, execution_state: ExecutionState,
                          iteration: int, result: OrchestratorResult) -> tuple:
        """判断阶段"""
        try:
            logger.info(f"判断阶段 (第{iteration}轮)")

            # 评估执行结果
            judge_result = await self.judge.evaluate_execution(plan, execution_state, iteration)

            result.judge_history.append(judge_result)

            logger.info(f"判断结果: satisfied={judge_result.satisfied}, confidence={judge_result.confidence}")

            # 根据判断结果决定下一步
            if judge_result.satisfied:
                # 满足条件，执行完成
                return OrchestratorState.DONE, judge_result
            elif judge_result.questions:
                # 需要向用户提问（暂时标记为失败，后续可以扩展）
                logger.info(f"需要向用户提问: {judge_result.questions}")
                return OrchestratorState.FAILED, judge_result
            elif iteration < self.max_iterations:
                # 不满足但可以重试，重新规划
                return OrchestratorState.PLAN, judge_result
            else:
                # 达到最大迭代次数，失败
                return OrchestratorState.FAILED, judge_result

        except Exception as e:
            logger.error(f"判断阶段失败: {e}")
            return OrchestratorState.FAILED, None

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


def get_orchestrator(max_iterations: int = 2, max_execution_time: float = 60.0) -> Orchestrator:
    """获取编排器实例"""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = Orchestrator(max_iterations, max_execution_time)
    return _orchestrator_instance


async def orchestrate_query(user_query: str,
                          context: Dict[str, Any] = None,
                          max_iterations: int = 2) -> OrchestratorResult:
    """
    编排用户查询的便捷函数

    Args:
        user_query: 用户查询
        context: 上下文信息
        max_iterations: 最大迭代次数

    Returns:
        OrchestratorResult: 执行结果
    """
    orchestrator = get_orchestrator(max_iterations=max_iterations)
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
