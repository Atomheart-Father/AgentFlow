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
        """构建系统提示词 - 只输出JSON"""
        return """你是一个AI规划专家。分析用户查询并制定执行计划。

可用工具：
- weather_get: 查询天气 {"location": "城市名", "date": "YYYY-MM-DD"}
- time_now: 获取当前时间 {}
- calendar_read: 查看日程 {"date": "YYYY-MM-DD"}
- file_read: 读取文件 {"file_path": "路径"}
- fs_write: 写入文件 {"path": "路径", "content": "内容"}
- path_planner: 规划文件路径（只接受filename和file_type参数）{"filename": "report", "file_type": "md"}
- ask_user: 询问用户 {"question": "问题"}
- math_calc: 数学计算 {"expression": "表达式"}
- web_search: 网络搜索 {"query": "搜索词", "max_results": 5}

规划规则：
1. 文件路径规划：写文件前必须先用path_planner规划正确路径（只接受filename和file_type参数）
2. 日期时间处理：当需要当前日期/时间时，必须使用time.now工具获取；遇到相对日期（如'明天'）时，先调用time.now再计算
3. 工具优先级：优先使用工具获取信息，其次利用已有上下文，最后才询问用户
4. 主观上下文用ask_user：城市/国别、个人偏好/预算、私有文件位置（明确未知的信息）
5. 客观信息用web_search：天气、新闻、价格、开放时间、官方事实
6. 组合策略：可先web_search给候选，再ask_user确认；或ask_user一次后超时转web_search
7. 硬约束：单轮最多1个ask_user，web_search≤2次

步骤类型：tool_call, summarize, write_file, ask_user

重要：
- 所有文件路径必须通过path_planner工具转换为系统路径后再写入！
- 永远不要直接询问日期，使用time.now工具！
- path_planner只接受filename和file_type参数！

只输出JSON格式，不要任何解释："""

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
      "tool": "weather_get",
      "inputs": {{"location": "北京"}},
      "depends_on": [],
      "expect": "天气信息",
      "output_key": "weather",
      "retry": 0
    }}
  ],
  "final_answer_template": "答案: {{weather}}"
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
