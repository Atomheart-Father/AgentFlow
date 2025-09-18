"""
Agent核心模块
处理用户输入，协调LLM调用，目前只做直连LLM和日志记录
"""
import asyncio
import json
from typing import Dict, Any, Optional, AsyncGenerator
from datetime import datetime

from llm_interface import get_llm_interface, LLMResponse
from config import get_config
from logger import get_logger
from tool_registry import get_tools, execute_tool, ToolError, to_openai_tools

logger = get_logger()

# M3编排器相关导入
try:
    from orchestrator import get_orchestrator, orchestrate_query, OrchestratorResult
    M3_AVAILABLE = True
except ImportError:
    M3_AVAILABLE = False
    logger.warning("M3编排器模块不可用，将使用传统模式")


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

    async def process_stream(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式处理用户输入

        Args:
            user_input: 用户输入
            context: 上下文信息

        Yields:
            Dict[str, Any]: 流式数据块
        """
        if self.llm.provider is None:
            raise RuntimeError("LLM提供者未初始化。请先调用 set_llm_interface() 设置有效的LLM接口，或调用 llm.initialize_provider()")

        start_time = datetime.now()
        logger.info(f"开始流式处理用户输入: {user_input[:100]}{'...' if len(user_input) > 100 else ''}")

        try:
            # 检查是否使用M3模式
            if self.use_m3 and hasattr(self, 'orchestrator'):
                logger.info("使用M3编排器模式处理查询")
                async for chunk in self._process_with_m3_stream(user_query=user_input, context=context):
                    yield chunk
                return

            # 初始化对话历史
            messages = []
            tool_call_trace = []
            max_tool_calls = 2  # 最多2次工具调用

            # 系统提示词
            system_prompt = self._build_system_prompt()
            messages.append({"role": "system", "content": system_prompt})

            # 用户输入（只添加一次）
            messages.append({"role": "user", "content": user_input})

            # 工具调用回路
            for tool_call_count in range(max_tool_calls + 1):
                logger.info(f"开始第 {tool_call_count + 1} 轮对话")

                # 准备工具模式
                tools_schema = None
                if self.tools and tool_call_count < max_tool_calls:
                    tools_schema = to_openai_tools(self.tools)
                    logger.debug(f"启用工具模式，共 {len(self.tools)} 个工具")

                # yield工具调用状态
                if tools_schema:
                    yield {
                        "type": "status",
                        "status": "thinking",
                        "message": f"🤔 正在思考和分析您的请求..."
                    }

                # 调用LLM（流式模式）
                try:
                    full_content = ""
                    function_calls = []

                    async for chunk in self.llm.generate_stream(
                        messages=messages,
                        tools_schema=tools_schema
                    ):
                        if chunk.get("type") == "content":
                            # 增量内容
                            yield {
                                "type": "content",
                                "content": chunk["content"],
                                "full_content": chunk["full_content"]
                            }
                            full_content = chunk["full_content"]

                        elif chunk.get("type") == "final":
                            # 最终结果
                            response = chunk["response"]
                            full_content = response.content
                            function_calls = response.function_calls or []
                            break

                        elif chunk.get("type") == "error":
                            # 错误
                            yield {
                                "type": "error",
                                "error": chunk["error"]
                            }
                            return

                    # 检查是否有工具调用
                    if function_calls:
                        logger.info(f"检测到 {len(function_calls)} 个工具调用")

                        # yield工具调用状态
                        yield {
                            "type": "status",
                            "status": "tool_call",
                            "message": f"🔧 正在调用工具..."
                        }

                        # 处理工具调用
                        tool_results = []
                        for tool_call in function_calls:
                            try:
                                # 处理新的OpenAI格式
                                if tool_call.get("type") == "function" and "function" in tool_call:
                                    func_info = tool_call["function"]
                                    tool_name = func_info.get("name")
                                    tool_args = func_info.get("arguments", {})
                                    if isinstance(tool_args, str):
                                        try:
                                            tool_args = json.loads(tool_args)
                                        except json.JSONDecodeError:
                                            tool_args = {}
                                    tool_call_id = tool_call.get("id")
                                else:
                                    # 兼容旧格式
                                    tool_name = tool_call.get("name")
                                    tool_args = tool_call.get("arguments", {})
                                    tool_call_id = tool_call.get("id")

                                # 更新tool_call格式用于后续处理
                                normalized_tool_call = {
                                    "id": tool_call_id,
                                    "name": tool_name,
                                    "arguments": tool_args
                                }

                                logger.info(f"执行工具: {tool_name}, 参数: {tool_args}")

                                # yield具体工具调用状态
                                yield {
                                    "type": "status",
                                    "status": "tool_executing",
                                    "message": f"🔧 正在执行 {tool_name}..."
                                }

                                # 特殊处理ask_user工具
                                if tool_name == "ask_user":
                                    # ask_user工具需要用户交互，返回特殊状态
                                    result = await self._execute_tool_call(normalized_tool_call)

                                    # yield ask_user状态，让前端显示输入界面
                                    yield {
                                        "type": "ask_user",
                                        "question": tool_args.get("question", "请提供更多信息"),
                                        "context": tool_args.get("context", ""),
                                        "tool_call": normalized_tool_call
                                    }
                                    # 不再继续处理，返回等待用户输入
                                    return

                                # 执行普通工具
                                result = await self._execute_tool_call(normalized_tool_call)

                                tool_results.append({
                                    "tool_call": normalized_tool_call,
                                    "result": result
                                })

                                tool_call_trace.append({
                                    "tool_name": tool_name,
                                    "args": tool_args,
                                    "result": result,
                                    "success": True
                                })

                                # yield工具执行结果
                                yield {
                                    "type": "tool_result",
                                    "tool_name": tool_name,
                                    "result": result
                                }

                            except Exception as e:
                                error_msg = f"工具 {tool_name} 执行失败: {str(e)}"
                                logger.error(error_msg)

                                tool_results.append({
                                    "tool_call": normalized_tool_call,
                                    "error": str(e)
                                })

                                tool_call_trace.append({
                                    "tool_name": tool_name,
                                    "args": tool_args,
                                    "error": str(e),
                                    "success": False
                                })

                        # 添加助手消息（包含tool_calls）
                        messages.append({
                            "role": "assistant",
                            "content": full_content,
                            "tool_calls": function_calls  # function_calls已经是正确的OpenAI格式
                        })

                        # 添加工具结果到消息历史（必须在assistant消息之后）
                        for tool_result in tool_results:
                            if "result" in tool_result:
                                messages.append({
                                    "role": "tool",
                                    "content": str(tool_result["result"]),
                                    "tool_call_id": tool_result["tool_call"].get("id")
                                })
                            else:
                                messages.append({
                                    "role": "tool",
                                    "content": f"工具执行失败: {tool_result['error']}",
                                    "tool_call_id": tool_result["tool_call"].get("id")
                                })

                        # yield继续思考状态
                        yield {
                            "type": "status",
                            "status": "thinking",
                            "message": f"💭 基于工具结果继续思考..."
                        }

                        continue  # 继续下一轮对话

                    else:
                        # 没有工具调用，结束对话
                        break

                except Exception as e:
                    logger.error(f"LLM调用异常: {e}")
                    # 如果是网络错误，重试
                    if "timeout" in str(e).lower() or "connection" in str(e).lower():
                        logger.info("检测到网络错误，等待后重试...")
                        import asyncio
                        await asyncio.sleep(2)
                        continue
                    else:
                        yield {
                            "type": "error",
                            "error": f"LLM调用异常: {str(e)}"
                        }
                        return

            # 计算响应时间
            response_time = (datetime.now() - start_time).total_seconds()

            # yield最终结果
            yield {
                "type": "final",
                "response": full_content,
                "metadata": {
                    "mode": "traditional",
                    "tool_call_trace": tool_call_trace,
                    "response_time": response_time,
                    "total_rounds": tool_call_count + 1
                }
            }

        except Exception as e:
            logger.error(f"流式处理失败: {e}")
            yield {
                "type": "error",
                "error": f"处理请求时发生错误: {str(e)}"
            }

    async def simple_chat(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> str:
        """简单问答接口 - 直接用Chat模型回答"""
        if self.llm.provider is None:
            raise RuntimeError("LLM提供者未初始化")

        try:
            messages = [
                {"role": "system", "content": "你是一个友好的AI助手，请直接回答用户的问题，保持简洁明了。"},
                {"role": "user", "content": user_input}
            ]

            response = await self.llm.generate(
                messages=messages,
                max_tokens=1000,
                temperature=0.7
            )

            return response.content.strip()

        except Exception as e:
            logger.error(f"简单问答失败: {e}")
            return f"抱歉，处理您的请求时出现错误: {str(e)}"

    async def _process_with_m3_stream(self, user_query: str, context: Optional[Dict[str, Any]] = None):
        """使用M3编排器处理查询（真·流式：assistant_content进聊天气泡，其他事件进状态栏）"""
        if not hasattr(self, 'orchestrator') or not self.orchestrator:
            yield {"type": "error", "message": "M3编排器未初始化"}
            return

        try:
            # 检查是否是续跑场景（context包含user_answer）
            is_resume = context and "user_answer" in context

            if is_resume:
                # 续跑场景：继续执行已有的任务
                print("[DEBUG] 检测到续跑场景，开始继续执行任务")
                yield {"type": "status", "message": "正在继续执行任务"}

                session_id = context.get("session_id")
                user_answer = context.get("user_answer")

                if session_id:
                    from orchestrator import get_session
                    session = get_session(session_id)

                    if session.active_task:
                        # 使用现有的任务状态继续执行
                        # 将用户答案添加到execution_state中
                        if session.active_task.execution_state:
                            # 查找等待用户输入的步骤，并设置答案
                            ask_user_pending = session.active_task.execution_state.get_artifact("ask_user_pending")
                            if ask_user_pending and isinstance(ask_user_pending, dict):
                                output_key = ask_user_pending.get("output_key", "user_location")
                                session.active_task.execution_state.set_artifact(output_key, user_answer)
                                # 清除ask_user_pending状态，防止重复询问
                                session.active_task.execution_state.set_artifact("ask_user_pending", None)
                                print(f"[DEBUG] 设置用户答案到 {output_key}: {user_answer}，清除ask_user_pending状态")

                        # 使用现有的active_task继续编排
                        result = await self.orchestrator.orchestrate(user_query="", context=context, active_task=session.active_task)
                    else:
                        # 没有活跃任务，重新规划
                        result = await self.orchestrator.orchestrate(user_query="", context=context)
                else:
                    result = await self.orchestrator.orchestrate(user_query="", context=context)
            else:
                # 正常规划场景
                print("[DEBUG] 发送状态事件: 正在规划任务")
                yield {"type": "status", "message": "正在规划任务"}

                # 模拟规划过程的思维链
                planning_steps = [
                    "分析用户查询意图...",
                    "制定执行计划...",
                    "准备调用相关工具...",
                    "优化执行步骤..."
                ]

                for step in planning_steps:
                    print(f"[DEBUG] 发送思维链: {step}")
                    yield {"type": "assistant_content", "content": step + " "}
                    await asyncio.sleep(0.1)

                # 执行编排
                result = await self.orchestrator.orchestrate(user_query=user_query, context=context)

            # 检查是否需要用户输入
            if result.status == "ask_user" and result.pending_questions:
                question = result.pending_questions[0]
                print(f"[DEBUG] 发送 ask_user 事件: {question}")
                yield {"type": "ask_user", "question": question, "context": "需要用户信息"}
                return  # 等待用户输入，不要继续执行

            # 检查是否处于等待用户输入状态
            if result.status == "waiting_for_user" and result.pending_questions:
                question = result.pending_questions[0]
                print(f"[DEBUG] 发送 ask_user 事件 (waiting状态): {question}")
                yield {"type": "ask_user", "question": question, "context": "需要用户信息"}
                return  # 等待用户输入，不要继续执行

            # 状态：开始执行
            print("[DEBUG] 发送状态事件: 正在执行任务")
            yield {"type": "status", "message": "正在执行任务"}

            # 模拟执行过程的思维链
            if result.final_plan and result.final_plan.steps:
                for i, step in enumerate(result.final_plan.steps, 1):
                    step_type_str = step.type.value if hasattr(step.type, 'value') else str(step.type)
                    print(f"[DEBUG] 发送工具轨迹: 执行步骤 {i}: {step_type_str}")
                    yield {"type": "tool_trace", "message": f"执行步骤 {i}: {step_type_str}"}

                    # 根据步骤类型显示不同的执行信息
                    if step.type == "tool_call" and hasattr(step, 'tool') and step.tool:
                        print(f"[DEBUG] 发送工具调用: 调用工具 {step.tool}")
                        yield {"type": "assistant_content", "content": f"\n调用工具 {step.tool}... "}
                    elif step.type == "web_search":
                        print(f"[DEBUG] 发送网络搜索: 搜索 {step.inputs.get('query', '')}")
                        yield {"type": "assistant_content", "content": f"\n执行网络搜索... "}
                    elif step.type == "ask_user":
                        print(f"[DEBUG] 发送用户询问: {step.inputs.get('question', '')}")
                        yield {"type": "assistant_content", "content": f"\n需要用户信息... "}
                    elif step.type == "summarize":
                        print(f"[DEBUG] 发送数据汇总: {step.expect}")
                        yield {"type": "assistant_content", "content": f"\n汇总分析数据... "}

                    await asyncio.sleep(0.1)

            # 处理最终结果
            final_content = ""

            if result.final_answer:
                # 有明确的最终答案
                final_content = "\n\n" + result.final_answer
            elif result.status == "completed" and hasattr(result, 'execution_state') and result.execution_state:
                # 任务完成但没有明确答案，从artifacts中构造有意义的响应
                artifacts = result.execution_state.artifacts
                response_parts = []

                # 提取有用的信息
                if "weather_data" in artifacts:
                    weather = artifacts["weather_data"]
                    if hasattr(weather, 'data') and weather.data:
                        response_parts.append(f"天气信息: {weather.data}")
                    elif isinstance(weather, dict):
                        response_parts.append(f"天气信息: {weather}")

                if "commute_tips" in artifacts:
                    tips = artifacts["commute_tips"]
                    if isinstance(tips, str):
                        response_parts.append(f"通勤建议: {tips}")
                    elif isinstance(tips, list):
                        response_parts.append("通勤建议:\n" + "\n".join(f"- {tip}" for tip in tips))

                if "file_path" in artifacts:
                    response_parts.append("文件已保存到指定位置")

                if response_parts:
                    final_content = "\n\n" + "\n\n".join(response_parts)
                else:
                    final_content = "\n\n任务已完成，所有步骤都已成功执行。"
            else:
                # 其他状态（如ask_user/waiting），不向聊天气泡写入误导性文本
                final_content = ""

            # 真·流式输出最终内容
            if final_content:
                print(f"[DEBUG] 发送最终内容: {final_content[:100]}...")
                yield {"type": "assistant_content", "content": final_content}

            # 状态：处理完成
            print("[DEBUG] 发送状态事件: 处理完成")
            yield {"type": "status", "message": "处理完成"}

        except Exception as e:
            logger.error(f"M3流式处理失败: {e}")
            yield {"type": "error", "message": f"处理失败: {str(e)}"}

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

            # 如果是ask_user状态，确保session中有active_task
            if orchestrator_result.status == "ask_user" and context and "session_id" in context:
                session_id = context["session_id"]
                from orchestrator import get_session
                session = get_session(session_id)

                # 创建active_task来保存当前状态
                if not session.active_task:
                    from orchestrator.orchestrator import ActiveTask
                    session.active_task = ActiveTask()
                    session.active_task.plan = orchestrator_result.final_plan
                    session.active_task.execution_state = orchestrator_result.execution_state
                    session.active_task.iteration_count = orchestrator_result.iteration_count
                    session.active_task.plan_iterations = orchestrator_result.plan_iterations
                    session.active_task.total_tool_calls = orchestrator_result.total_tool_calls
                    print(f"[DEBUG] 为session {session_id} 创建了active_task")

            # 检查是否处于ask_user状态
            if orchestrator_result.status == "ask_user" and orchestrator_result.execution_state:
                ask_user_data = orchestrator_result.execution_state.get_artifact("ask_user_pending")
                if ask_user_data:
                    response = f"🤔 {ask_user_data['question']}\n\n请告诉我您的答案，我将继续为您处理请求。"
                    metadata = {
                        "mode": "m3_orchestrator",
                        "status": "ask_user",
                        "ask_user_pending": ask_user_data,
                        "final_plan": orchestrator_result.final_plan,
                        "execution_state": orchestrator_result.execution_state,
                        "timestamp": start_time.isoformat()
                    }
                    return {
                        "response": response,
                        "metadata": metadata
                    }

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
- For file writing: Call file_write (supports path aliases like "桌面", "下载", "文档")
- For asking user information (location, date, etc.): Call ask_user

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
