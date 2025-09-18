"""
Executor模块 - 负责执行计划中的步骤
使用DeepSeek-V3/V3.1 (deepseek-chat) 进行工具调用和执行
"""
import asyncio
import json
from typing import Dict, Any, List, Optional, Union
from datetime import datetime

from llm_interface import create_llm_interface_with_keys
from schemas.plan import Plan, PlanStep, StepType
from tool_registry import get_tools, execute_tool, ToolError
from logger import get_logger

logger = get_logger()


class AskUserException(Exception):
    """用户询问异常 - 表示需要用户输入"""

    def __init__(self, ask_user_data: Dict[str, Any]):
        self.ask_user_data = ask_user_data
        super().__init__(f"需要用户回答: {ask_user_data['question']}")


class ExecutionState:
    """执行状态管理"""

    def __init__(self):
        self.artifacts: Dict[str, Any] = {}  # 步骤产出
        self.inputs: Dict[str, Any] = {}     # 用户输入
        self.errors: List[str] = []          # 执行错误
        self.completed_steps: List[str] = [] # 已完成的步骤

    def set_artifact(self, key: str, value: Any):
        """设置步骤产出"""
        self.artifacts[key] = value
        logger.debug(f"设置产出: {key} = {str(value)[:100]}...")

    def get_artifact(self, key: str) -> Any:
        """获取步骤产出"""
        return self.artifacts.get(key)

    def interpolate_inputs(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """插值替换输入参数中的变量"""
        result = {}

        for key, value in inputs.items():
            if isinstance(value, str):
                # 替换 {{variable}} 格式的变量
                for artifact_key, artifact_value in self.artifacts.items():
                    placeholder = "{{" + artifact_key + "}}"
                    if placeholder in value:
                        if isinstance(artifact_value, (dict, list)):
                            # 对于复杂对象，使用JSON序列化
                            value = value.replace(placeholder, json.dumps(artifact_value, ensure_ascii=False))
                        else:
                            value = value.replace(placeholder, str(artifact_value))

                # 替换 {{user_input}} 等特殊变量
                for input_key, input_value in self.inputs.items():
                    placeholder = "{{" + input_key + "}}"
                    if placeholder in value:
                        value = value.replace(placeholder, str(input_value))

            result[key] = value

        return result


class Executor:
    """执行器类"""

    def __init__(self):
        """初始化执行器"""
        # 使用DeepSeek-V3进行执行
        self.llm = create_llm_interface_with_keys()
        # 确保使用deepseek-chat模型
        if hasattr(self.llm.config, 'deepseek_model'):
            original_model = self.llm.config.deepseek_model
            self.llm.config.deepseek_model = "deepseek-chat"
            logger.info(f"Executor使用执行模型: {original_model} -> deepseek-chat")

        self.tools = get_tools()
        self.max_tool_calls_per_step = 2

    async def execute_plan(self, plan: Plan, user_inputs: Dict[str, Any] = None) -> ExecutionState:
        """
        执行完整计划

        Args:
            plan: 执行计划
            user_inputs: 用户输入（可选）

        Returns:
            ExecutionState: 执行状态
        """
        state = ExecutionState()
        if user_inputs:
            state.inputs.update(user_inputs)

        logger.info(f"开始执行计划，共 {len(plan.steps)} 个步骤")

        # 按依赖关系排序步骤
        sorted_steps = self._topological_sort(plan.steps)

        for step in sorted_steps:
            try:
                logger.info(f"执行步骤: {step.id} ({step.type})")
                await self._execute_step(step, state, plan)

                # 标记步骤为完成
                state.completed_steps.append(step.id)

            except AskUserException as e:
                # 遇到用户询问，保存状态并返回等待用户输入的状态
                logger.info(f"步骤 {step.id} 需要用户输入: {e.ask_user_data['question']}")
                state.set_artifact(f"ask_user_pending", e.ask_user_data)
                return state  # 返回当前状态，等待用户输入

            except Exception as e:
                error_msg = f"步骤 {step.id} 执行失败: {str(e)}"
                logger.error(error_msg)
                state.errors.append(error_msg)

                # 如果是关键步骤失败，可能需要停止执行
                if step.retry == 0:
                    logger.warning(f"步骤 {step.id} 重试次数已用完，停止执行")
                    break

        logger.info(f"计划执行完成，已完成 {len(state.completed_steps)}/{len(plan.steps)} 个步骤")
        return state

    async def _execute_step(self, step: PlanStep, state: ExecutionState, plan: Plan):
        """执行单个步骤"""
        # 插值替换输入参数
        interpolated_inputs = state.interpolate_inputs(step.inputs)

        if step.type == StepType.TOOL_CALL:
            await self._execute_tool_call(step, interpolated_inputs, state)

        elif step.type == StepType.READ:
            await self._execute_read(step, interpolated_inputs, state)

        elif step.type == StepType.SUMMARIZE:
            await self._execute_summarize(step, interpolated_inputs, state)

        elif step.type == StepType.ASK_USER:
            await self._execute_ask_user(step, interpolated_inputs, state)

        else:
            raise ValueError(f"不支持的步骤类型: {step.type}")

    async def _execute_tool_call(self, step: PlanStep, inputs: Dict[str, Any], state: ExecutionState):
        """执行工具调用"""
        if not step.tool:
            raise ValueError(f"工具调用步骤 {step.id} 缺少tool字段")

        # 检查工具是否存在
        if not any(tool.name == step.tool for tool in self.tools):
            raise ValueError(f"工具 {step.tool} 不存在")

        logger.info(f"调用工具: {step.tool} 参数: {inputs}")

        # 执行工具
        result = execute_tool(step.tool, self.tools, **inputs)

        # 保存结果
        state.set_artifact(step.output_key, result)

    async def _execute_read(self, step: PlanStep, inputs: Dict[str, Any], state: ExecutionState):
        """执行读取操作"""
        # 这里可以调用文件读取工具或其他读取操作
        logger.info(f"执行读取操作: {inputs}")

        # 简单的读取实现（可以扩展）
        result = f"读取操作完成: {inputs}"
        state.set_artifact(step.output_key, result)

    async def _execute_summarize(self, step: PlanStep, inputs: Dict[str, Any], state: ExecutionState):
        """执行总结操作"""
        # 使用LLM进行总结
        data_to_summarize = inputs.get('data', '')
        summary_prompt = f"请总结以下内容：\n\n{data_to_summarize}"

        messages = [
            {"role": "system", "content": "你是一个专业的总结助手，请简洁准确地总结内容。"},
            {"role": "user", "content": summary_prompt}
        ]

        response = await self.llm.generate(
            messages=messages,
            max_tokens=512
        )

        result = response.content.strip()
        state.set_artifact(step.output_key, result)
        logger.info(f"总结完成: {result[:100]}...")

    async def _execute_ask_user(self, step: PlanStep, inputs: Dict[str, Any], state: ExecutionState):
        """执行用户询问操作"""
        question = inputs.get('question', '请提供更多信息')

        # 保存问题到状态中，等待外部处理
        ask_user_data = {
            "question": question,
            "step_id": step.id,
            "output_key": step.output_key,
            "timestamp": datetime.now().isoformat(),
            "status": "waiting"  # waiting, answered, cancelled
        }

        state.set_artifact(f"ask_user_{step.id}", ask_user_data)
        logger.info(f"需要用户回答问题: {question}")

        # 抛出特殊异常，表示需要用户输入
        raise AskUserException(ask_user_data)

    def _topological_sort(self, steps: List[PlanStep]) -> List[PlanStep]:
        """拓扑排序步骤（处理依赖关系）"""
        # 简单的依赖关系排序（可以优化为真正的拓扑排序）
        sorted_steps = []
        remaining = steps.copy()

        while remaining:
            # 找到没有未满足依赖的步骤
            executable = []
            for step in remaining:
                deps_satisfied = all(dep in [s.id for s in sorted_steps] for dep in step.depends_on)
                if deps_satisfied:
                    executable.append(step)

            if not executable:
                # 有循环依赖或无法执行的步骤
                logger.warning("检测到无法执行的步骤，跳过依赖检查")
                sorted_steps.extend(remaining)
                break

            # 按ID排序执行
            executable.sort(key=lambda s: s.id)
            sorted_steps.extend(executable)

            # 从剩余列表中移除已执行的步骤
            for step in executable:
                remaining.remove(step)

        return sorted_steps

    async def execute_single_step(self, step: PlanStep, state: ExecutionState) -> Dict[str, Any]:
        """执行单个步骤（用于调试）"""
        logger.info(f"单独执行步骤: {step.id}")

        try:
            await self._execute_step(step, state, None)
            return {
                "success": True,
                "result": state.get_artifact(step.output_key),
                "error": None
            }
        except Exception as e:
            return {
                "success": False,
                "result": None,
                "error": str(e)
            }


# 全局执行器实例
_executor_instance = None


def get_executor() -> Executor:
    """获取执行器实例"""
    global _executor_instance
    if _executor_instance is None:
        _executor_instance = Executor()
    return _executor_instance


async def execute_plan_async(plan: Plan, user_inputs: Dict[str, Any] = None) -> ExecutionState:
    """
    执行计划的便捷函数

    Args:
        plan: 执行计划
        user_inputs: 用户输入

    Returns:
        ExecutionState: 执行状态
    """
    executor = get_executor()
    return await executor.execute_plan(plan, user_inputs)


if __name__ == "__main__":
    # 测试执行器
    async def test_executor():
        from schemas.plan import create_sample_plan

        executor = Executor()
        sample_plan = create_sample_plan()

        try:
            state = await executor.execute_plan(sample_plan)
            print("✅ 执行成功:")
            print(f"产出数量: {len(state.artifacts)}")
            print(f"错误数量: {len(state.errors)}")

            for key, value in state.artifacts.items():
                print(f"产出 {key}: {str(value)[:100]}...")

        except Exception as e:
            print(f"❌ 执行失败: {e}")

    asyncio.run(test_executor())
