"""
Judge模块 - 负责判断执行结果并决定下一步
使用DeepSeek-R1 (deepseek-reasoner) 进行推理判断
"""
import json
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from llm_interface import create_llm_interface_with_keys
from schemas.orchestrator import PlannerOutput, JudgeOutput, validate_judge_output, Plan
from orchestrator.executor import ExecutionState
from config import get_config
from telemetry import get_telemetry_logger, TelemetryStage, TelemetryEvent
from logger import get_logger

logger = get_logger()


class JudgeResult:
    """判断结果"""

    def __init__(self,
                 satisfied: bool,
                 missing: List[str] = None,
                 plan_patch: Dict[str, Any] = None,
                 questions: List[str] = None,
                 confidence: float = 0.0):
        self.satisfied = satisfied
        self.missing = missing or []
        self.plan_patch = plan_patch or {}
        self.questions = questions or []
        self.confidence = confidence

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "satisfied": self.satisfied,
            "missing": self.missing,
            "plan_patch": self.plan_patch,
            "questions": self.questions,
            "confidence": self.confidence
        }


class Judge:
    """判断器类"""

    def __init__(self):
        """初始化判断器"""
        config = get_config()

        # 使用配置中的Judge模型
        self.llm = create_llm_interface_with_keys()
        if hasattr(self.llm.config, 'model_provider'):
            # 强制使用judge模型配置
            original_provider = self.llm.config.model_provider
            self.llm.config.model_provider = "deepseek"
            if hasattr(self.llm.config, 'deepseek_model'):
                original_model = self.llm.config.deepseek_model
                self.llm.config.deepseek_model = config.judge_model
                logger.info(f"Judge切换模型: {original_model} -> {config.judge_model}")

        self.max_retries = 2
        self.max_tokens = config.max_tokens_per_stage
        self.temperature = config.judge_temperature
        self.telemetry = get_telemetry_logger()

    async def evaluate_execution(self,
                               plan: PlannerOutput,
                               state: ExecutionState,
                               iteration: int = 1) -> JudgeOutput:
        """
        评估执行结果

        Args:
            plan: 原始计划
            state: 执行状态
            iteration: 当前迭代次数

        Returns:
            JudgeResult: 判断结果
        """
        logger.info(f"开始判断执行结果 (第{iteration}轮)")

        # 构建系统提示词
        system_prompt = self._build_system_prompt()

        # 构建用户提示词
        user_prompt = self._build_user_prompt(plan, state, iteration)

        for attempt in range(self.max_retries + 1):
            try:
                # 调用DeepSeek-R1进行判断
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]

                response = await self.llm.generate(
                    messages=messages,
                    force_json=True,  # 强制JSON输出
                    max_tokens=self.max_tokens,
                    temperature=self.temperature
                )

                # 解析判断结果（严格JSON模式）
                judge_result = validate_judge_output(response.content)

                # Telemetry: 记录判断结果
                if not judge_result.satisfied:
                    # SPEC_MISMATCH: 产物不满足success_criteria
                    self.telemetry.log_event(
                        stage=TelemetryStage.JUDGE,
                        event=TelemetryEvent.SPEC_MISMATCH,
                        user_query="",  # 需要从上下文获取
                        context={
                            "iteration": iteration,
                            "missing": judge_result.missing,
                            "questions": judge_result.questions
                        },
                        plan_excerpt={"goal": plan.goal, "success_criteria": plan.success_criteria},
                        model={"judge": self.llm.config.deepseek_model}
                    )

                logger.info(f"✅ 判断完成: satisfied={judge_result.satisfied}")
                return judge_result

            except Exception as e:
                logger.error(f"判断失败 (尝试 {attempt + 1}): {e}")
                if attempt < self.max_retries:
                    await asyncio.sleep(1)
                    continue
                else:
                    # 返回保守的判断结果
                    return JudgeOutput(
                        satisfied=False,
                        missing=["判断过程出错"],
                        questions=["能否重新描述您的问题？"]
                    )

    def _build_system_prompt(self) -> str:
        """构建系统提示词 - 只输出JSON"""
        return """评估执行结果是否满足要求。只输出JSON：{satisfied,bool, missing[], plan_patch?, questions?}。

评估规则：
- satisfied为true：所有success_criteria都已满足，产出完整可用
- satisfied为false：若能靠补全信息解决，返回1个高质量追问；否则给plan_patch修正计划
- missing：明确列出缺失的关键信息
- plan_patch：可选，包含修正步骤的字典
- questions：最多2个，向用户追问的问题列表

严格按JSON格式输出，不要任何解释。"""

    def _build_user_prompt(self, plan: PlannerOutput, state: ExecutionState, iteration: int) -> str:
        """构建用户提示词"""
        prompt_parts = [
            f"原始目标：{plan.goal}",
            "",
            f"成功标准：",
        ]

        for i, criterion in enumerate(plan.success_criteria, 1):
            prompt_parts.append(f"{i}. {criterion}")

        prompt_parts.extend([
            "",
            f"已完成的步骤：{len(state.completed_steps)}/{len(plan.steps)}",
            "",
            "执行产出："
        ])

        for key, value in state.artifacts.items():
            if isinstance(value, (dict, list)):
                value_str = json.dumps(value, ensure_ascii=False, indent=2)
            else:
                value_str = str(value)
            prompt_parts.append(f"- {key}: {value_str[:200]}{'...' if len(value_str) > 200 else ''}")

        if state.errors:
            prompt_parts.extend([
                "",
                "执行错误："
            ])
            for error in state.errors:
                prompt_parts.append(f"- {error}")

        prompt_parts.extend([
            "",
            f"当前是第{iteration}轮执行",
            "",
            "请判断是否满足成功标准，并按以下JSON格式输出：",
            "",
            "{",
            '  "satisfied": true,',
            '  "missing": ["缺失的信息1", "缺失的信息2"],',
            '  "plan_patch": {"steps": [...]},',
            '  "questions": ["问题1", "问题2"],',
            '  "confidence": 0.85',
            "}",
            "",
            "重要：只输出JSON，不要任何解释！"
        ])

        return "\n".join(prompt_parts)



# 全局判断器实例
_judge_instance = None


def get_judge() -> Judge:
    """获取判断器实例"""
    global _judge_instance
    if _judge_instance is None:
        _judge_instance = Judge()
    return _judge_instance


async def evaluate_execution_async(plan: PlannerOutput,
                                   state: ExecutionState,
                                   iteration: int = 1) -> JudgeOutput:
    """
    评估执行结果的便捷函数

    Args:
        plan: 执行计划
        state: 执行状态
        iteration: 当前迭代次数

    Returns:
        JudgeResult: 判断结果
    """
    judge = get_judge()
    return await judge.evaluate_execution(plan, state, iteration)


if __name__ == "__main__":
    # 测试判断器
    async def test_judge():
        from schemas.plan import create_sample_plan
        from orchestrator.executor import ExecutionState

        judge = Judge()
        sample_plan = create_sample_plan()
        sample_state = ExecutionState()

        # 模拟一些执行结果
        # 注意：这里不再模拟执行结果，而是通过实际执行获取结果
        print("注意：此测试已被移除，避免任何模拟行为")

    # 测试函数已被移除，避免模拟行为
