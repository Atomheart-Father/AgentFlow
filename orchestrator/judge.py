"""
Judge模块 - 负责判断执行结果并决定下一步
使用DeepSeek-R1 (deepseek-reasoner) 进行推理判断
"""
import json
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from llm_interface import create_llm_interface_with_keys
from schemas.plan import Plan
from orchestrator.executor import ExecutionState
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
        # 使用DeepSeek-R1进行推理判断
        self.llm = create_llm_interface_with_keys()
        # 强制使用deepseek-reasoner模型
        if hasattr(self.llm.config, 'deepseek_model'):
            original_model = self.llm.config.deepseek_model
            self.llm.config.deepseek_model = "deepseek-reasoner"
            logger.info(f"Judge切换到推理模型: {original_model} -> deepseek-reasoner")

        self.max_retries = 2
        self.max_tokens = 1024

    async def evaluate_execution(self,
                               plan: Plan,
                               state: ExecutionState,
                               iteration: int = 1) -> JudgeResult:
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
                    max_tokens=self.max_tokens
                )

                # 解析判断结果
                result_data = self._parse_judge_response(response.content)
                judge_result = JudgeResult(**result_data)

                logger.info(f"✅ 判断完成: satisfied={judge_result.satisfied}, confidence={judge_result.confidence}")
                return judge_result

            except Exception as e:
                logger.error(f"判断失败 (尝试 {attempt + 1}): {e}")
                if attempt < self.max_retries:
                    await asyncio.sleep(1)
                    continue
                else:
                    # 返回保守的判断结果
                    return JudgeResult(
                        satisfied=False,
                        missing=["判断过程出错"],
                        questions=["能否重新描述您的问题？"],
                        confidence=0.0
                    )

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        return """你是AI系统的质量评估专家。你的任务是：
1. 检查执行结果是否满足成功标准
2. 识别缺失的信息或证据
3. 决定是否需要重新规划或向用户提问
4. 提供具体的改进建议

评估原则：
- 基于事实和证据进行判断
- 如果信息不完整，优先考虑向用户提问而不是猜测
- 最多建议2个追问问题
- 给出0-1之间的置信度分数

请严格按照以下JSON格式输出判断结果，不要添加任何额外内容："""

    def _build_user_prompt(self, plan: Plan, state: ExecutionState, iteration: int) -> str:
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

    def _parse_judge_response(self, response: str) -> Dict[str, Any]:
        """解析判断响应"""
        try:
            # 尝试直接解析JSON
            result = json.loads(response.strip())

            # 验证必需字段
            required_fields = ['satisfied', 'confidence']
            for field in required_fields:
                if field not in result:
                    raise ValueError(f"缺少必需字段: {field}")

            # 设置默认值
            if 'missing' not in result:
                result['missing'] = []
            if 'plan_patch' not in result:
                result['plan_patch'] = {}
            if 'questions' not in result:
                result['questions'] = []

            return result

        except json.JSONDecodeError:
            # 尝试提取JSON部分
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass

            # 如果都失败了，返回保守的结果
            logger.warning(f"无法解析判断响应: {response[:200]}...")
            return {
                "satisfied": False,
                "missing": ["响应解析失败"],
                "plan_patch": {},
                "questions": ["能否重新描述您的问题？"],
                "confidence": 0.0
            }


# 全局判断器实例
_judge_instance = None


def get_judge() -> Judge:
    """获取判断器实例"""
    global _judge_instance
    if _judge_instance is None:
        _judge_instance = Judge()
    return _judge_instance


async def evaluate_execution_async(plan: Plan,
                                 state: ExecutionState,
                                 iteration: int = 1) -> JudgeResult:
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
