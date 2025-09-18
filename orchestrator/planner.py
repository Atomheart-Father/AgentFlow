"""
Planner模块 - 负责规划和制定执行计划
使用DeepSeek-R1 (deepseek-reasoner) 进行推理规划
"""
import json
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime

from llm_interface import create_llm_interface_with_keys
from schemas.plan import Plan, PlanValidationError, validate_plan
from logger import get_logger

logger = get_logger()


class Planner:
    """规划器类"""

    def __init__(self):
        """初始化规划器"""
        # 使用DeepSeek-R1进行推理规划
        self.llm = create_llm_interface_with_keys()
        # 强制使用deepseek-reasoner模型
        if hasattr(self.llm.config, 'deepseek_model'):
            original_model = self.llm.config.deepseek_model
            self.llm.config.deepseek_model = "deepseek-reasoner"
            logger.info(f"Planner切换到推理模型: {original_model} -> deepseek-reasoner")

        self.max_retries = 2
        self.max_tokens = 2048

    async def create_plan(self, user_query: str, context: Dict[str, Any] = None) -> Plan:
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
                    max_tokens=self.max_tokens
                )

                # 解析和验证计划
                plan_data = self._parse_plan_response(response.content)
                validated_plan = validate_plan(plan_data)

                logger.info(f"✅ 规划成功，共 {len(validated_plan.steps)} 个步骤")
                return validated_plan

            except PlanValidationError as e:
                logger.warning(f"计划验证失败 (尝试 {attempt + 1}): {e}")
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
        """构建系统提示词"""
        return """你是AI系统的规划专家。你的任务是：
1. 分析用户查询，理解用户真正需要什么
2. 制定详细的执行步骤来满足用户需求
3. 每个步骤都要明确"预期产出"，便于后续验证
4. 严格控制步骤数量（最多6步）
5. 优先使用工具调用来获取准确信息

可用工具及参数格式：
- time_now: 获取当前时间信息
  参数: {} (无需参数)

- weather_get: 查询天气
  参数格式: {"location": "城市名"} (如北京、上海等)

- calendar_read: 查看日程安排
  参数格式: {"date": "YYYY-MM-DD"} (可选)

- email_list: 查看邮件
  参数格式: {"limit": 10} (可选)

- file_read: 读取文件内容
  参数格式: {"file_path": "文件路径"}

- file_write: 写入文件内容
  参数格式: {"file_path": "文件路径（如'桌面/报告.md'、'下载/文件.txt'）", "content": "文件内容"}

- ask_user: 询问用户信息
  参数格式: {"question": "具体问题", "context": "上下文说明（可选）"}

- math_calc: 执行数学计算
  参数格式: {"expression": "计算表达式"}

规划原则：
- 工具调用步骤最多5次（支持更复杂的多步骤任务）
- 每个步骤都要有明确的evidence预期
- 依赖关系要清晰
- 最终答案要基于工具结果
- 使用最简单的参数格式，不要添加多余的描述

信息获取策略：
- 当需要获取用户信息时，使用ask_user工具询问用户
- 不要假设用户的默认信息，总是通过ask_user工具获取必要信息
- ask_user工具会触发前端交互界面，用户可以直接回复

步骤类型选择：
- tool_call: 调用工具获取信息（包括ask_user工具来询问用户信息）
- process: 对已有信息进行分析处理

请严格按照以下JSON格式输出计划，不要添加任何额外内容："""

    def _build_user_prompt(self, user_query: str, context: Dict[str, Any]) -> str:
        """构建用户提示词"""
        prompt_parts = [
            f"用户查询：{user_query}",
            "",
            "请制定执行计划，严格按照以下JSON格式：",
            "",
            "{",
            '  "goal": "简要描述目标",',
            '  "success_criteria": ["标准1", "标准2"],',
            '  "max_steps": 6,',
            '  "steps": [',
            '    {',
            '      "id": "s1",',
            '      "type": "tool_call",',
            '      "tool": "time_now",',
            '      "inputs": {},',
            '      "depends_on": [],',
            '      "expect": "具体的证据预期",',
            '      "output_key": "result_key",',
            '      "retry": 1',
            '    },',
            '    {',
            '      "id": "s2",',
            '      "type": "tool_call",',
            '      "tool": "ask_user",',
            '      "inputs": {"question": "请告诉我您的位置"},',
            '      "depends_on": [],',
            '      "expect": "用户提供位置信息",',
            '      "output_key": "user_location",',
            '      "retry": 0',
            '    }',
            '  ],',
            '  "final_answer_template": "最终答案模板 {{result_key}}"',
            "}",
            "",
            "重要：只输出JSON，不要任何解释或额外内容！"
        ]

        return "\n".join(prompt_parts)

    def _parse_plan_response(self, response: str) -> Dict[str, Any]:
        """解析规划响应"""
        try:
            # 尝试直接解析JSON
            return json.loads(response.strip())
        except json.JSONDecodeError:
            # 尝试提取JSON部分
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass

            # 如果都失败了，抛出异常
            raise PlanValidationError(f"无法解析规划响应为JSON: {response[:200]}...")

    def _create_fallback_plan(self, user_query: str) -> Plan:
        """创建后备计划"""
        logger.warning("使用后备计划")

        # 简单的后备计划：直接回答用户查询
        return Plan(
            goal=f"回答用户查询：{user_query}",
            success_criteria=["提供合理的回答"],
            max_steps=2,
            steps=[
                {
                    "id": "s1",
                    "type": "summarize",
                    "tool": None,
                    "inputs": {"query": user_query},
                    "depends_on": [],
                    "expect": "理解用户查询并准备回答",
                    "output_key": "analysis",
                    "retry": 0
                }
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


async def plan_query(user_query: str, context: Dict[str, Any] = None) -> Plan:
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
