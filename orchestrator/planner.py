"""
Planner模块 - 负责规划和制定执行计划
使用DeepSeek-R1 (deepseek-reasoner) 进行推理规划
"""
import json
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime

from llm_interface import create_llm_interface_with_keys
from schemas.orchestrator import PlannerOutput, validate_planner_output, StepType
from config import get_config
from telemetry import get_telemetry_logger, TelemetryStage, TelemetryEvent
from logger import get_logger

logger = get_logger()


class Planner:
    """规划器类"""

    def __init__(self):
        """初始化规划器"""
        config = get_config()

        # 使用配置中的Planner模型
        self.llm = create_llm_interface_with_keys()
        if hasattr(self.llm.config, 'model_provider'):
            # 强制使用planner模型配置
            original_provider = self.llm.config.model_provider
            self.llm.config.model_provider = "deepseek"
            if hasattr(self.llm.config, 'deepseek_model'):
                original_model = self.llm.config.deepseek_model
                self.llm.config.deepseek_model = config.planner_model
                logger.info(f"Planner切换模型: {original_model} -> {config.planner_model}")

        self.max_retries = 2
        self.max_tokens = config.max_tokens_per_stage
        self.temperature = config.planner_temperature
        self.telemetry = get_telemetry_logger()

    async def create_plan(self, user_query: str, context: Dict[str, Any] = None) -> PlannerOutput:
        """
        为用户查询创建执行计划

        Args:
            user_query: 用户查询
            context: 上下文信息（可选）

        Returns:
            Plan: 执行计划
        """
        if context is None:
            context = {}

        # 构建系统提示词
        system_prompt = self._build_system_prompt()

        # 构建用户提示词
        user_prompt = self._build_user_prompt(user_query, context)

        logger.info(f"开始规划用户查询: {user_query[:100]}...")

        for attempt in range(self.max_retries + 1):
            try:
                # 调用DeepSeek-R1进行规划
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

                # 解析和验证计划（严格JSON模式）
                validated_plan = validate_planner_output(response.content)

                # 检查规划质量
                if len(validated_plan.steps) == 0:
                    # Telemetry: 空计划
                    self.telemetry.log_event(
                        stage=TelemetryStage.PLAN,
                        event=TelemetryEvent.PLAN_EMPTY_OR_USELESS,
                        user_query=user_query,
                        context={"reason": "empty_plan", "raw_response": response.content[:500]},
                        plan_excerpt={"goal": validated_plan.goal, "steps_count": 0},
                        model={"planner": self.llm.config.deepseek_model}
                    )

                logger.info(f"✅ 规划成功，共 {len(validated_plan.steps)} 个步骤")
                return validated_plan

            except ValueError as e:
                logger.warning(f"计划验证失败 (尝试 {attempt + 1}): {e}")

                # Telemetry: 记录规划JSON验证失败
                self.telemetry.log_event(
                    stage=TelemetryStage.PLAN,
                    event=TelemetryEvent.PLANNER_NON_JSON,
                    user_query=user_query,
                    context={"error": str(e), "attempt": attempt + 1, "raw_response": response.content[:500]},
                    model={"planner": self.llm.config.deepseek_model}
                )

                if attempt < self.max_retries:
                    continue
                else:
                    # 返回一个简单的默认计划
                    return self._create_fallback_plan(user_query)

            except Exception as e:
                logger.error(f"规划失败 (尝试 {attempt + 1}): {e}")
                if attempt < self.max_retries:
                    await asyncio.sleep(1)  # 等待后重试
                    continue
                else:
                    raise e

        # 这行代码不会被执行到，但为了类型检查
        raise Exception("规划失败，已达到最大重试次数")

    def _build_system_prompt(self) -> str:
        """构建系统提示词 - 强化硬规则，只输出JSON"""
        return """你是一个AI规划专家。分析用户查询并制定执行计划。

你可以使用以下工具完成任务。凡是涉及"当前日期/时间/星期几/相对日期（今天/明天/后天/今晚等）"，先调用 time.now 获取基准时间（Europe/Amsterdam），再做日期归一化；不要向用户询问"今天几号"。凡是需要落盘的结果，调用 fs_write 直接写入到环境配置的目录中。

重要规则：
- 查询天气/日程/位置相关信息时，如果用户没有明确指定城市/地点，必须使用ask_user询问用户所在位置
- 只有在用户明确指定了城市/地点，或者从上下文可以明确推断出位置时，才直接使用工具查询
- 用户查询中包含"我"、"我的"等主语时，优先考虑需要询问用户的场景

可用工具：
- time_now: 获取当前日期和时间（Europe/Amsterdam时区）{}
- weather_get: 查询天气 {"location": "城市名", "date": "YYYY-MM-DD"}
- calendar_read: 查看日程 {"date": "YYYY-MM-DD"}
- file_read: 读取文件 {"file_path": "路径"}
- fs_write: 写入文件到配置目录 {"filename": "文件名", "content": "内容", "format": "md/txt/json"}
- ask_user: 询问用户 {"question": "问题"}
- math_calc: 数学计算 {"expression": "表达式"}
- web_search: 网络搜索 {"query": "搜索词", "max_results": 5}

强化硬规则：
1. 【仅JSON输出】：禁止任何自然语言和多余字段，只输出JSON格式结果
2. 【失败重试】：解析失败时自动重试1次
3. 【时间强规则】：涉及日期/相对日，必须先time.now（Europe/Amsterdam）并归一化
4. 【成功准则示例】：has_tomorrow_precip、has_three_commute_tips、file_written_true
5. 【文件写入规则】：直接使用fs_write工具，传入filename、content、format参数
6. 【变量引用格式】：summarize和write_file步骤的inputs必须使用{{variable}}格式引用前置步骤的output_key
7. 【工具优先级】：time.now → 其他工具 → 已有上下文 → AskUser（仅主观信息）
8. 【AskUser限制】：只用于城市/预算/个人偏好等主观信息，绝不为日期/时间发问
9. 【组合策略】：可先web_search给候选，再ask_user确认；或ask_user一次后超时转web_search
10. 【硬约束】：单轮最多1个ask_user，web_search≤2次

仅输出 JSON：{goal, success_criteria[], max_steps, steps[], final_answer_template}。steps[].type ∈ {"tool_call","summarize","write_file","ask_user"}，并写明 expect 和 output_key。禁止生成任何非 JSON 文本。"""

    def _build_user_prompt(self, user_query: str, context: Dict[str, Any]) -> str:
        """构建用户提示词 - 只输出JSON"""
        return f"""为以下用户查询制定执行计划：

{user_query}

输出JSON格式：
{{
  "goal": "任务目标",
  "success_criteria": ["成功标准1", "成功标准2"],
  "max_steps": 5,
  "steps": [
    {{
      "id": "s1",
      "type": "tool_call",
      "tool": "time_now",
      "inputs": {{}},
      "depends_on": [],
      "expect": "获取当前时间用于日期计算",
      "output_key": "current_time",
      "retry": 0
    }},
    {{
      "id": "s2",
      "type": "ask_user",
      "inputs": {{"question": "您想查询哪个城市的天气？"}},
      "depends_on": [],
      "expect": "获取用户所在城市",
      "output_key": "user_location",
      "retry": 0
    }},
    {{
      "id": "s3",
      "type": "tool_call",
      "tool": "weather_get",
      "inputs": {{"location": "{{user_location}}", "date": "{{current_time.tomorrow_date}}"}},
      "depends_on": ["s1", "s2"],
      "expect": "获取指定城市的天气信息",
      "output_key": "weather",
      "retry": 0
    }},
    {{
      "id": "s4",
      "type": "summarize",
      "inputs": {{"weather": "{{weather}}", "location": "{{user_location}}"}},
      "depends_on": ["s3"],
      "expect": "基于天气信息规划行程建议",
      "output_key": "plan",
      "retry": 0
    }},
    {{
      "id": "s5",
      "type": "tool_call",
      "tool": "fs_write",
      "inputs": {{"filename": "weather_plan", "content": "{{plan}}", "format": "md"}},
      "depends_on": ["s4"],
      "expect": "将行程计划写入文件",
      "output_key": "file_written",
      "retry": 0
    }}
  ],
  "final_answer_template": "天气: {{weather}}, 行程: {{plan}}, 文件已写入"
}}"""

    def _create_fallback_plan(self, user_query: str) -> PlannerOutput:
        """创建后备计划"""
        logger.warning("使用后备计划")

        # 简单的后备计划：直接回答用户查询
        from schemas.orchestrator import PlanStep

        return PlannerOutput(
            goal=f"回答用户查询：{user_query}",
            success_criteria=["提供合理的回答"],
            max_steps=2,
            steps=[
                PlanStep(
                    id="s1",
                    type=StepType.SUMMARIZE,
                    inputs={"query": user_query},
                    depends_on=[],
                    expect="理解用户查询并准备回答",
                    output_key="analysis",
                    retry=0
                )
            ],
            final_answer_template="基于您的查询，我来帮您解答。"
        )


# 全局规划器实例
_planner_instance = None


def get_planner() -> Planner:
    """获取规划器实例"""
    global _planner_instance
    if _planner_instance is None:
        _planner_instance = Planner()
    return _planner_instance


async def plan_query(user_query: str, context: Dict[str, Any] = None) -> PlannerOutput:
    """
    规划用户查询的便捷函数

    Args:
        user_query: 用户查询
        context: 上下文信息

    Returns:
        Plan: 执行计划
    """
    planner = get_planner()
    return await planner.create_plan(user_query, context)


if __name__ == "__main__":
    # 测试规划器
    async def test_planner():
        planner = Planner()
        test_query = "现在几点了？今天是星期几？"

        try:
            plan = await planner.create_plan(test_query)
            print("✅ 规划成功:")
            print(f"目标: {plan.goal}")
            print(f"步骤数量: {len(plan.steps)}")
            for i, step in enumerate(plan.steps, 1):
                print(f"步骤{i}: {step.type} - {step.tool or '无工具'}")

        except Exception as e:
            print(f"❌ 规划失败: {e}")

    asyncio.run(test_planner())
