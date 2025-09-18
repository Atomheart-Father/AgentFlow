"""
Agent核心模块
处理用户输入，协调LLM调用，目前只做直连LLM和日志记录
"""
import asyncio
import json
from typing import Dict, Any, Optional
from datetime import datetime

from llm_interface import get_llm_interface, LLMResponse
from config import get_config
from logger import get_logger
from tool_registry import get_tools, execute_tool, ToolError, to_openai_tools

# M3编排器相关导入
try:
    from orchestrator import get_orchestrator, orchestrate_query, OrchestratorResult
    M3_AVAILABLE = True
except ImportError:
    M3_AVAILABLE = False
    logger.warning("M3编排器模块不可用，将使用传统模式")

logger = get_logger()


class AgentCore:
    """Agent核心类"""

    def __init__(self, llm_interface=None, use_m3: bool = False):
        self.config = get_config()
        self.llm = llm_interface or get_llm_interface()
        self.use_m3 = use_m3 and M3_AVAILABLE

        # 初始化工具系统
        if self.config.tools_enabled:
            self.tools = get_tools()
            logger.info(f"工具系统已加载: {len(self.tools)} 个工具")
        else:
            self.tools = []
            logger.info("工具系统已禁用")

        # 初始化M3编排器
        if self.use_m3:
            self.orchestrator = get_orchestrator()
            logger.info("M3编排器模式已启用")
        else:
            logger.info("传统Agent模式已启用")

        logger.info("Agent核心初始化完成", extra={
            "provider": self.config.model_provider,
            "rag_enabled": self.config.rag_enabled,
            "tools_enabled": self.config.tools_enabled,
            "tools_count": len(self.tools),
            "use_m3": self.use_m3,
            "llm_initialized": self.llm.provider is not None
        })

    def set_llm_interface(self, llm_interface) -> None:
        """
        设置LLM接口

        Args:
            llm_interface: LLM接口实例
        """
        self.llm = llm_interface
        logger.info("LLM接口已更新", extra={
            "provider": self.config.model_provider,
            "llm_initialized": self.llm.provider is not None
        })

    async def process(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        处理用户输入

        Args:
            user_input: 用户输入文本
            context: 上下文信息（预留）

        Returns:
            Dict包含响应内容和元数据
        """
        if self.llm.provider is None:
            raise RuntimeError("LLM提供者未初始化。请先调用 set_llm_interface() 设置有效的LLM接口，或调用 llm.initialize_provider()")

        start_time = datetime.now()
        logger.info(f"开始处理用户输入: {user_input[:100]}{'...' if len(user_input) > 100 else ''}")

        try:
            # 检查是否使用M3模式
            if self.use_m3 and hasattr(self, 'orchestrator'):
                logger.info("使用M3编排器模式处理查询")
                return await self._process_with_m3(user_query=user_input, context=context)

            # 初始化对话历史
            messages = []
            tool_call_trace = []
            max_tool_calls = 2  # 最多2次工具调用

            # 系统提示词
            system_prompt = self._build_system_prompt()
            messages.append({"role": "system", "content": system_prompt})

            # 用户输入
            messages.append({"role": "user", "content": user_input})

            # 工具调用回路
            for tool_call_count in range(max_tool_calls + 1):
                logger.info(f"开始第 {tool_call_count + 1} 轮对话")

                # 准备工具模式
                tools_schema = None
                if self.tools and tool_call_count < max_tool_calls:
                    tools_schema = to_openai_tools(self.tools)
                    logger.debug(f"启用工具模式，共 {len(self.tools)} 个工具")
                    logger.debug(f"工具schema: {tools_schema}")
                    logger.debug(f"当前消息列表: {messages}")

                # 调用LLM（传递messages而不是prompt）
                try:
                    llm_response = await self.llm.generate(
                        messages=messages,  # 传递消息列表
                        tools_schema=tools_schema
                    )
                except Exception as e:
                    logger.error(f"LLM调用异常: {e}")
                    # 如果是网络错误，重试
                    if "timeout" in str(e).lower() or "connection" in str(e).lower():
                        logger.info("检测到网络错误，等待后重试...")
                        import asyncio
                        await asyncio.sleep(2)
                        continue
                    else:
                        raise e

                # 处理LLM响应
                assistant_message = {"role": "assistant", "content": llm_response.content}

                # 检查是否有工具调用
                if llm_response.function_calls:
                    logger.info(f"检测到 {len(llm_response.function_calls)} 个工具调用")

                    # 构建正确的tool_calls格式
                    tool_calls = []
                    for tool_call in llm_response.function_calls:
                        if hasattr(tool_call, 'function'):
                            # OpenAI对象格式，转换为标准格式
                            tool_calls.append({
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": tool_call.function.name,
                                    "arguments": tool_call.function.arguments if isinstance(tool_call.function.arguments, str) else json.dumps(tool_call.function.arguments)
                                }
                            })
                        else:
                            # 已经是字典格式，转换为正确格式
                            if "function" not in tool_call:
                                # 需要构建function字段
                                tool_calls.append({
                                    "id": tool_call.get("id", ""),
                                    "type": tool_call.get("type", "function"),
                                    "function": {
                                        "name": tool_call.get("name", ""),
                                        "arguments": tool_call.get("arguments", {}) if isinstance(tool_call.get("arguments"), str) else json.dumps(tool_call.get("arguments", {}))
                                    }
                                })
                            else:
                                tool_calls.append(tool_call)

                    assistant_message["tool_calls"] = tool_calls
                    messages.append(assistant_message)

                    # 执行工具调用
                    tool_results = []
                    for tool_call in llm_response.function_calls:
                        tool_result = await self._execute_tool_call(tool_call)
                        tool_results.append(tool_result)

                        # 添加工具结果消息
                        tool_message = {
                            "role": "tool",
                            "content": str(tool_result["result"]),
                            "tool_call_id": tool_call["id"]
                        }
                        messages.append(tool_message)

                        # 记录工具调用轨迹
                        if hasattr(tool_call, 'function'):
                            # OpenAI对象格式
                            tool_name = tool_call.function.name
                            arguments = tool_call.function.arguments
                        else:
                            # 字典格式
                            tool_name = tool_call.get("name", "")
                            arguments = tool_call.get("arguments", {})

                        tool_call_trace.append({
                            "tool_name": tool_name,
                            "arguments": arguments,
                            "result": tool_result["result"],
                            "error": tool_result.get("error"),
                            "execution_time": tool_result["execution_time"]
                        })

                    # 如果有工具调用，继续下一轮对话
                    continue
                else:
                    # 没有工具调用，直接返回最终答案
                    messages.append(assistant_message)
                    break

            # 计算总处理时间
            total_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"处理总时间: {total_time:.2f}s")

            # 构建返回结果
            result = {
                "response": llm_response.content,
                "metadata": {
                    "model": llm_response.model,
                    "response_time": llm_response.response_time,
                    "total_time": total_time,
                    "usage": llm_response.usage,
                    "function_calls": llm_response.function_calls,
                    "tool_call_trace": tool_call_trace,
                    "conversation_rounds": len([m for m in messages if m["role"] == "assistant"]),
                    "timestamp": start_time.isoformat()
                }
            }

            return result

        except Exception as e:
            error_msg = f"处理用户输入时发生错误: {str(e)}"
            logger.error(error_msg, exc_info=True)

            return {
                "response": "抱歉，处理您的请求时出现了错误，请稍后重试。",
                "metadata": {
                    "error": str(e),
                    "timestamp": start_time.isoformat(),
                    "total_time": (datetime.now() - start_time).total_seconds()
                }
            }

    async def _process_with_m3(self, user_query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        使用M3编排器处理用户查询

        Args:
            user_query: 用户查询
            context: 上下文信息

        Returns:
            处理结果字典
        """
        start_time = datetime.now()

        try:
            # 使用编排器处理查询
            orchestrator_result = await self.orchestrator.orchestrate(user_query, context)

            # 转换结果格式以保持与传统模式的兼容性
            response = orchestrator_result.final_answer or "处理完成，但无法生成最终答案。"

            # 构建元数据
            metadata = {
                "mode": "m3_orchestrator",
                "status": orchestrator_result.status,
                "iteration_count": orchestrator_result.iteration_count,
                "total_time": orchestrator_result.total_time,
                "timestamp": start_time.isoformat(),
                "plan_steps": len(orchestrator_result.final_plan.steps) if orchestrator_result.final_plan else 0,
                "execution_artifacts": len(orchestrator_result.execution_state.artifacts) if orchestrator_result.execution_state else 0,
                "judge_history": [jr.to_dict() for jr in orchestrator_result.judge_history]
            }

            # 如果有工具调用轨迹，添加到元数据中
            if orchestrator_result.execution_state:
                tool_trace = []
                for step_id in orchestrator_result.execution_state.completed_steps:
                    # 这里可以添加更详细的工具调用信息
                    tool_trace.append({
                        "step_id": step_id,
                        "status": "completed"
                    })
                metadata["tool_call_trace"] = tool_trace

            # 如果执行失败，添加错误信息
            if orchestrator_result.error_message:
                metadata["error"] = orchestrator_result.error_message
                if "失败" in orchestrator_result.status:
                    response = f"处理失败：{orchestrator_result.error_message}"

            logger.info(f"M3编排器处理完成: {orchestrator_result.status}, 耗时{orchestrator_result.total_time:.2f}s")

            return {
                "response": response,
                "metadata": metadata
            }

        except Exception as e:
            logger.error(f"M3编排器处理失败: {e}", exc_info=True)

            return {
                "response": "M3编排器处理失败，已回退到传统模式。",
                "metadata": {
                    "mode": "m3_fallback",
                    "error": str(e),
                    "timestamp": start_time.isoformat(),
                    "total_time": (datetime.now() - start_time).total_seconds()
                }
            }

    def _build_system_prompt(self) -> str:
        """
        构建系统提示词（支持工具调用）

        Returns:
            系统提示词
        """
        base_prompt = """你是AI个人助理，可以帮助用户处理各种任务。

你具备以下能力：
1. 基础对话和问答
2. 工具调用能力 - 你可以调用工具来获取外部信息"""

        if self.tools:
            tool_names = [tool.name for tool in self.tools]
            base_prompt += f"\n3. 可用工具: {', '.join(tool_names)}"

        base_prompt += """

INSTRUCTIONS:
You are a helpful AI assistant with access to tools. When a user asks a question that requires external information, you MUST call the appropriate tool.

TOOL USAGE RULES:
- For time-related questions (current time, day of week, date): Call time_now
- For weather queries: Call weather_get
- For math calculations: Call math_calc
- For calendar/schedule queries: Call calendar_read
- For email queries: Call email_list
- For web searches: Call web_search
- For file reading: Call file_read

IMPORTANT: Always call the appropriate tool when external information is needed. Do not provide generic responses."""

        return base_prompt

    def _build_prompt(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        构建传统提示词（向后兼容）

        Args:
            user_input: 用户输入
            context: 上下文信息

        Returns:
            完整的提示词
        """
        system_prompt = self._build_system_prompt()

        if context:
            # 如果有上下文，添加到提示词中
            context_str = "\n".join([f"{k}: {v}" for k, v in context.items()])
            prompt = f"{system_prompt}\n\n上下文信息:\n{context_str}\n\n用户: {user_input}"
        else:
            prompt = f"{system_prompt}\n\n用户: {user_input}"

        return prompt

    async def _execute_tool_call(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行单个工具调用

        Args:
            tool_call: 工具调用信息

        Returns:
            工具执行结果
        """
        import time
        start_time = time.time()

        try:
            # 调试：打印tool_call对象的类型和结构
            logger.debug(f"Tool call object type: {type(tool_call)}")
            logger.debug(f"Tool call object: {tool_call}")
            logger.debug(f"Tool call dir: {[attr for attr in dir(tool_call) if not attr.startswith('_')]}")

            # 处理OpenAI工具调用对象
            if hasattr(tool_call, 'function'):
                # OpenAI工具调用对象
                logger.debug(f"Tool call has function attribute: {hasattr(tool_call.function, 'name')}")
                tool_name = tool_call.function.name
                arguments = tool_call.function.arguments
                tool_call_id = tool_call.id
                logger.debug(f"Extracted from OpenAI object: name={tool_name}, id={tool_call_id}")
            elif isinstance(tool_call, dict):
                # 字典格式（从llm_interface转换而来）
                tool_name = tool_call.get("name", "")
                arguments = tool_call.get("arguments", {})
                tool_call_id = tool_call.get("id", "")
                logger.debug(f"Extracted from dict: name={tool_name}, id={tool_call_id}, dict_keys={list(tool_call.keys())}")
            else:
                # 字典格式（向后兼容）
                tool_name = tool_call.get("function", {}).get("name", "")
                arguments = tool_call.get("function", {}).get("arguments", "{}")
                tool_call_id = tool_call.get("id", "")
                logger.debug(f"Extracted from legacy dict: name={tool_name}, id={tool_call_id}")

            # 解析参数（如果是字符串）
            if isinstance(arguments, str):
                try:
                    import json
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}

            logger.info(f"执行工具: {tool_name}, 参数: {arguments}")

            # 执行工具
            result = execute_tool(tool_name, self.tools, **arguments)

            execution_time = time.time() - start_time

            return {
                "tool_call_id": tool_call_id,
                "result": result,
                "execution_time": execution_time,
                "success": True
            }

        except ToolError as e:
            execution_time = time.time() - start_time
            logger.error(f"工具执行失败: {e}")

            # 获取tool_call_id
            if hasattr(tool_call, 'id'):
                tool_call_id = tool_call.id
            else:
                tool_call_id = tool_call.get("id", "")

            return {
                "tool_call_id": tool_call_id,
                "result": f"工具调用失败: {e.message}",
                "error": str(e),
                "execution_time": execution_time,
                "success": False,
                "retryable": e.retryable
            }

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"工具执行异常: {e}")

            # 获取tool_call_id
            if hasattr(tool_call, 'id'):
                tool_call_id = tool_call.id
            else:
                tool_call_id = tool_call.get("id", "")

            return {
                "tool_call_id": tool_call_id,
                "result": f"工具执行异常: {str(e)}",
                "error": str(e),
                "execution_time": execution_time,
                "success": False,
                "retryable": False
            }

    def _log_response(self, llm_response: LLMResponse, user_input: str):
        """
        记录LLM响应信息

        Args:
            llm_response: LLM响应对象
            user_input: 用户输入
        """
        # 记录基本信息
        logger.info("LLM响应完成", extra={
            "model": llm_response.model,
            "response_time": ".2f",
            "content_length": len(llm_response.content),
            "has_function_calls": llm_response.function_calls is not None
        })

        # 如果启用DEBUG模式，记录更多详细信息
        if self.config.log_level == "DEBUG":
            logger.debug("详细响应信息", extra={
                "user_input": user_input[:200] + "..." if len(user_input) > 200 else user_input,
                "response_content": llm_response.content[:500] + "..." if len(llm_response.content) > 500 else llm_response.content,
                "usage": llm_response.usage,
                "function_calls": llm_response.function_calls
            })

        # 记录token使用情况
        if llm_response.usage:
            usage_info = []
            if "total_tokens" in llm_response.usage:
                usage_info.append(f"总token: {llm_response.usage['total_tokens']}")
            if "prompt_tokens" in llm_response.usage:
                usage_info.append(f"输入token: {llm_response.usage['prompt_tokens']}")
            if "completion_tokens" in llm_response.usage:
                usage_info.append(f"输出token: {llm_response.usage['completion_tokens']}")

            if usage_info:
                logger.info(f"Token使用情况: {' | '.join(usage_info)}")


# 全局实例（默认不初始化LLM，供独立测试使用）
agent_core = AgentCore()


def get_agent_core() -> AgentCore:
    """获取Agent核心实例"""
    return agent_core


def create_agent_core_with_llm(use_m3: bool = False) -> AgentCore:
    """创建带有LLM初始化的Agent核心实例"""
    from llm_interface import create_llm_interface_with_keys
    llm = create_llm_interface_with_keys()
    return AgentCore(llm_interface=llm, use_m3=use_m3)


async def process_message(user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    便捷函数：处理单个消息

    Args:
        user_input: 用户输入
        context: 上下文

    Returns:
        处理结果
    """
    return await agent_core.process(user_input, context)
