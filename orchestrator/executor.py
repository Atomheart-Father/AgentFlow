"""
Executor模块 - 负责执行计划中的步骤
使用DeepSeek-V3/V3.1 (deepseek-chat) 进行工具调用和执行
"""
import asyncio
import json
from typing import Dict, Any, List, Optional, Union
from datetime import datetime

from llm_interface import create_llm_interface_with_keys
from schemas.orchestrator import PlannerOutput, PlanStep, StepType, Plan
from tool_registry import get_tools, execute_tool, ToolError
from schemas.tool_result import StandardToolResult
from telemetry import get_telemetry_logger, TelemetryStage, TelemetryEvent
from logger import get_logger

logger = get_logger()


# AskUserException已移除，现在通过ask_user工具处理


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
                        # 特殊处理不同类型的结果
                        if artifact_key == "file_path" and isinstance(artifact_value, dict) and "resolved_path" in artifact_value:
                            # path_planner的结果：提取resolved_path
                            replacement = artifact_value["resolved_path"]
                        elif isinstance(artifact_value, StandardToolResult):
                            # 工具结果：提取data字段
                            if artifact_value.ok and artifact_value.data is not None:
                                if isinstance(artifact_value.data, dict):
                                    # 如果是字典，尝试提取有意义的内容
                                    if "current_time" in artifact_value.data:
                                        replacement = artifact_value.data["current_time"]
                                    elif "temperature" in artifact_value.data:
                                        replacement = f"{artifact_value.data.get('temperature', 'N/A')}°C"
                                    else:
                                        replacement = json.dumps(artifact_value.data, ensure_ascii=False)
                                else:
                                    replacement = str(artifact_value.data)
                            else:
                                replacement = f"[工具调用失败: {artifact_value.error.message if artifact_value.error else '未知错误'}]"
                        elif isinstance(artifact_value, dict):
                            # 其他字典对象
                            if "current_time" in artifact_value:
                                replacement = artifact_value["current_time"]
                            else:
                                replacement = json.dumps(artifact_value, ensure_ascii=False)
                        elif isinstance(artifact_value, list):
                            replacement = json.dumps(artifact_value, ensure_ascii=False)
                        else:
                            replacement = str(artifact_value)

                        value = value.replace(placeholder, replacement)

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
        from config import get_config
        config = get_config()

        # 使用配置中的Executor模型
        self.llm = create_llm_interface_with_keys()
        if hasattr(self.llm.config, 'model_provider'):
            # 强制使用executor模型配置
            self.llm.config.model_provider = "deepseek"
            if hasattr(self.llm.config, 'deepseek_model'):
                self.llm.config.deepseek_model = config.executor_model
                logger.info(f"Executor使用执行模型: {config.executor_model}")

        self.tools = get_tools()
        self.max_tool_calls_per_step = 2
        self.telemetry = get_telemetry_logger()

    async def execute_plan(self, plan: PlannerOutput, user_inputs: Dict[str, Any] = None, max_tool_calls: int = None) -> ExecutionState:
        """
        执行完整计划

        Args:
            plan: 执行计划
            user_inputs: 用户输入（可选）
            max_tool_calls: 最大工具调用次数限制

        Returns:
            ExecutionState: 执行状态
        """
        state = ExecutionState()
        if user_inputs:
            state.inputs.update(user_inputs)

        logger.info(f"开始执行计划，共 {len(plan.steps)} 个步骤")

        # 初始化工具调用计数
        tool_call_count = 0

        # 按依赖关系排序步骤
        sorted_steps = self._topological_sort(plan.steps)

        for step in sorted_steps:
            # 检查工具调用预算
            if max_tool_calls is not None and tool_call_count >= max_tool_calls:
                logger.warning(f"达到工具调用上限 {max_tool_calls}，停止执行")
                break

            try:
                logger.info(f"执行步骤: {step.id} ({step.type})")
                step_tool_calls = await self._execute_step(step, state, plan)

                # 更新工具调用计数
                tool_call_count += step_tool_calls

                # 如果在步骤执行过程中产生了待询问用户的问题，则立即暂停执行，等待用户输入
                if state.get_artifact("ask_user_pending"):
                    logger.info("检测到ask_user_pending，暂停执行等待用户输入")
                    return state

                # 标记步骤为完成（仅当未进入等待用户输入状态时）
                state.completed_steps.append(step.id)

            except Exception as e:
                # 记录执行错误
                error_msg = f"步骤 {step.id} 执行失败: {str(e)}"
                logger.error(error_msg)
                state.errors.append(error_msg)

                # 如果是关键步骤失败，可能需要停止执行
                if step.retry == 0:
                    logger.warning(f"步骤 {step.id} 重试次数已用完，停止执行")
                    break

        logger.info(f"计划执行完成，已完成 {len(state.completed_steps)}/{len(plan.steps)} 个步骤")
        return state

    async def _execute_step(self, step: PlanStep, state: ExecutionState, plan: PlannerOutput) -> int:
        """执行单个步骤"""
        # 插值替换输入参数
        interpolated_inputs = state.interpolate_inputs(step.inputs)

        if step.type == StepType.TOOL_CALL:
            await self._execute_tool_call(step, interpolated_inputs, state)
            return 1  # 工具调用算作一次

        elif step.type == StepType.SUMMARIZE:
            await self._execute_summarize(step, interpolated_inputs, state)
            return 0

        elif step.type == StepType.WRITE_FILE:
            await self._execute_write_file(step, interpolated_inputs, state)
            return 0

        elif step.type == StepType.ASK_USER:
            await self._execute_ask_user(step, interpolated_inputs, state)
            return 0

        else:
            raise ValueError(f"不支持的步骤类型: {step.type}")

    async def _execute_tool_call(self, step: PlanStep, inputs: Dict[str, Any], state: ExecutionState):
        """执行工具调用"""
        if not step.tool:
            raise ValueError(f"工具调用步骤 {step.id} 缺少tool字段")

        # 参数映射：将常见的参数名映射为工具期望的参数名
        mapped_inputs = self._map_tool_parameters(step.tool, inputs)

        # 前置校验：对于weather_get，若缺少location，触发ask_user闭环
        if step.tool == "weather_get":
            location_value = mapped_inputs.get("location")
            if not isinstance(location_value, str) or not location_value.strip():
                state.set_artifact("ask_user_pending", {
                    "questions": ["请告诉我要查询天气的城市（例如：Rotterdam, NL）"],
                    "expects": "city",
                    "step_id": step.id
                })
                logger.info("weather_get缺少location，已触发ASK_USER等待城市信息")
                return

        # Telemetry: 参数验证（如果参数无效）
        try:
            # 这里可以添加参数验证逻辑
            logger.info(f"调用工具: {step.tool} 参数: {mapped_inputs}")
        except Exception as e:
            self.telemetry.log_event(
                stage=TelemetryStage.ACT,
                event=TelemetryEvent.EXEC_PARAM_INVALID,
                user_query="",  # 需要从上下文获取
                context={
                    "tool": step.tool,
                    "step_id": step.id,
                    "error": str(e),
                    "inputs": inputs,
                    "mapped_inputs": mapped_inputs
                }
            )
            raise

        # 执行工具
        result = execute_tool(step.tool, self.tools, **mapped_inputs)

        # 检查工具执行结果
        if isinstance(result, StandardToolResult) and not result.ok:
            # Telemetry: 工具执行失败
            self.telemetry.log_event(
                stage=TelemetryStage.ACT,
                event=TelemetryEvent.EXEC_TOOL_FAIL,
                user_query="",  # 需要从上下文获取
                context={
                    "tool": step.tool,
                    "step_id": step.id,
                    "error": result.error.dict() if result.error else {},
                    "inputs": mapped_inputs
                },
                model={"executor": self.llm.config.deepseek_model}
            )

        # 保存结果
        state.set_artifact(step.output_key, result)

    def _map_tool_parameters(self, tool_name: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """映射工具参数名，将常见的参数名转换为工具期望的参数名，并处理相对日期"""
        mapped = inputs.copy()

        # 相对日期处理：遇到相对日期词，使用date_normalize进行归一化（Europe/Amsterdam）
        for key, value in mapped.items():
            if isinstance(value, str):
                # 处理相对日期词
                relative_date_keywords = ["明天", "后天", "今天", "tomorrow", "day after tomorrow", "today"]
                v_lower = value.lower()
                if any(keyword in v_lower for keyword in relative_date_keywords):
                    try:
                        norm = execute_tool("date_normalize", self.tools, date=value, timezone="Europe/Amsterdam")
                        if isinstance(norm, StandardToolResult) and norm.ok and norm.data and "normalized_date" in norm.data:
                            mapped[key] = norm.data["normalized_date"]
                    except Exception as e:
                        logger.warning(f"相对日期处理失败: {e}")

        # weather_get工具的参数映射
        if tool_name == "weather_get":
            # 处理各种可能的参数格式
            if "city" in mapped and "location" not in mapped:
                # 将city映射为location
                mapped["location"] = mapped.pop("city")

            # 处理location参数
            if "location" in mapped:
                location_value = mapped["location"]
                # 处理默认城市描述
                if isinstance(location_value, str):
                    if "Rotterdam" in location_value:
                        mapped["location"] = "Rotterdam"
                    # 如果是其他城市名，直接使用

            # 不再设置默认城市，缺少时交由上游触发ASK_USER

        # file_read工具的参数映射
        elif tool_name == "file_read":
            if "file_path" in mapped and "path" not in mapped:
                mapped["path"] = mapped.pop("file_path")
            # file_read工具必须指定文件路径，不设置默认值

        # time_now工具不需要参数
        elif tool_name == "time_now":
            # 确保参数为空
            return {}

        # math_calc工具的参数映射
        elif tool_name == "math_calc":
            if "expression" not in mapped and "query" in mapped:
                mapped["expression"] = mapped.pop("query")

        return mapped

    async def _execute_read(self, step: PlanStep, inputs: Dict[str, Any], state: ExecutionState):
        """执行读取操作"""
        # 这里可以调用文件读取工具或其他读取操作
        logger.info(f"执行读取操作: {inputs}")

        # 简单的读取实现（可以扩展）
        result = f"读取操作完成: {inputs}"
        state.set_artifact(step.output_key, result)

    async def _execute_summarize(self, step: PlanStep, inputs: Dict[str, Any], state: ExecutionState):
        """执行总结操作"""
        # 智能汇总输入：优先使用data/text/content，否则拼接所有键值
        summary_text = None
        for key in ["data", "text", "content"]:
            if key in inputs and inputs[key]:
                summary_text = inputs[key]
                break

        if summary_text is None:
            # 将所有输入键值拼接为文本
            import json as _json
            parts = []
            for k, v in inputs.items():
                if isinstance(v, (dict, list)):
                    parts.append(f"{k}: {_json.dumps(v, ensure_ascii=False)}")
                else:
                    parts.append(f"{k}: {v}")
            summary_text = "\n".join(parts) if parts else "(无内容)"

        messages = [
            {"role": "system", "content": "你是一个专业的总结助手，请简洁准确地总结内容。"},
            {"role": "user", "content": f"请总结以下内容：\n\n{summary_text}"}
        ]

        response = await self.llm.generate(
            messages=messages,
            max_tokens=512
        )

        result = response.content.strip()
        state.set_artifact(step.output_key, result)
        logger.info(f"总结完成: {result[:100]}...")

    async def _execute_write_file(self, step: PlanStep, inputs: Dict[str, Any], state: ExecutionState):
        """执行写文件步骤"""
        # 使用fs_write工具
        result = execute_tool("fs_write", self.tools, **inputs)
        state.set_artifact(step.output_key, result)
        logger.info(f"写文件步骤 {step.id} 完成，输出到: {step.output_key}")

    async def _execute_ask_user(self, step: PlanStep, inputs: Dict[str, Any], state: ExecutionState):
        """执行询问用户步骤"""
        # 使用ask_user工具
        result = execute_tool("ask_user", self.tools, **inputs)
        state.set_artifact(step.output_key, result)
        logger.info(f"询问用户步骤 {step.id} 完成，输出到: {step.output_key}")

    # _execute_ask_user已移除，现在通过ask_user工具处理

    async def _execute_process(self, step: PlanStep, inputs: Dict[str, Any], state: ExecutionState):
        """执行推理处理步骤"""
        # 构建处理提示
        process_prompt = f"请基于以下输入数据进行推理处理：\n\n"
        process_prompt += f"任务描述: {step.expect}\n\n"

        # 添加输入数据
        for key, value in inputs.items():
            if isinstance(value, dict):
                process_prompt += f"{key}: {json.dumps(value, ensure_ascii=False, indent=2)}\n\n"
            else:
                process_prompt += f"{key}: {value}\n\n"

        process_prompt += "请根据任务描述，对输入数据进行分析和处理，给出结果。"

        messages = [
            {"role": "system", "content": "你是一个专业的推理助手，请基于提供的输入数据进行分析和处理。"},
            {"role": "user", "content": process_prompt}
        ]

        response = await self.llm.generate(
            messages=messages,
            max_tokens=1024
        )

        result = response.content.strip()
        state.set_artifact(step.output_key, result)
        logger.info(f"推理处理完成: {result[:100]}...")

    async def _execute_reasoning(self, step: PlanStep, inputs: Dict[str, Any], state: ExecutionState):
        """执行推理步骤"""
        # 推理步骤与处理步骤类似，使用LLM进行推理
        await self._execute_process(step, inputs, state)

    async def _execute_response_generation(self, step: PlanStep, inputs: Dict[str, Any], state: ExecutionState):
        """执行响应生成步骤"""
        # 响应生成步骤也是使用LLM生成内容
        await self._execute_process(step, inputs, state)

    async def _execute_output(self, step: PlanStep, inputs: Dict[str, Any], state: ExecutionState):
        """执行输出步骤"""
        # 输出步骤通常是整合信息，不需要LLM调用
        # 直接将输入数据作为输出
        output_data = {}
        for key, value in inputs.items():
            if isinstance(value, dict):
                output_data.update(value)
            else:
                output_data[key] = value

        state.set_artifact(step.output_key, output_data)
        logger.info(f"输出步骤完成: {len(output_data)} 个数据项")


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


async def execute_plan_async(plan: PlannerOutput, user_inputs: Dict[str, Any] = None) -> ExecutionState:
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
