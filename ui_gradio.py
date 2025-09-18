"""
Gradio用户界面
提供聊天界面，将用户输入传递给Agent核心处理
包含心跳机制防止长时间无用掉线
"""
import asyncio
import threading
import time
import uuid
from datetime import datetime
import gradio as gr
from typing import List, Tuple, Dict, Any, Optional

from agent_core import create_agent_core_with_llm
from config import get_config
from logger import setup_logging, get_logger
from orchestrator import get_orchestrator

# 初始化日志
config = get_config()
setup_logging(config.log_level)
logger = get_logger()


class ChatUI:
    """聊天UI类"""

    def __init__(self):
        self.config = config
        self.chat_history: List[Tuple[str, str]] = []
        self.metadata_history: List[Dict[str, Any]] = []

        # 历史聊天记录管理（预留RAG数据库接口）
        self.rag_store = None  # 未来接入RAG数据库
        self.current_conversation_id: Optional[str] = None
        # 临时内存存储，未来替换为RAG查询
        self.temp_conversation_cache: Dict[str, Dict[str, Any]] = {}

        # 会话状态管理
        self.session_id: Optional[str] = None

        # 默认使用M3编排器模式
        self.use_m3_mode = True
        self.agent = create_agent_core_with_llm(use_m3=True)
        self.orchestrator = get_orchestrator()

        # 心跳机制
        self.heartbeat_thread = None
        self.heartbeat_active = False
        self.last_activity = time.time()

    def start_heartbeat(self):
        """启动心跳机制"""
        if self.heartbeat_thread is None or not self.heartbeat_thread.is_alive():
            self.heartbeat_active = True
            self.heartbeat_thread = threading.Thread(target=self._heartbeat_worker, daemon=True)
            self.heartbeat_thread.start()
            logger.info("心跳机制已启动")

    def stop_heartbeat(self):
        """停止心跳机制"""
        self.heartbeat_active = False
        if self.heartbeat_thread:
            self.heartbeat_thread.join(timeout=2)
        logger.info("心跳机制已停止")

    def _heartbeat_worker(self):
        """心跳工作线程"""
        while self.heartbeat_active:
            try:
                # 每30秒发送一次心跳
                time.sleep(30)
                current_time = time.time()

                # 检查是否有活动（如果超过5分钟没有活动，认为需要心跳）
                if current_time - self.last_activity > 300:  # 5分钟
                    logger.debug("发送心跳保持连接")
                    # 这里可以添加轻量的健康检查调用
                    # 比如检查agent是否正常工作

                # 检查内存使用情况
                # 在长时间运行时，这有助于发现潜在问题

            except Exception as e:
                logger.warning(f"心跳机制异常: {e}")

    def update_activity(self):
        """更新最后活动时间"""
        self.last_activity = time.time()

    def switch_mode(self, use_m3: bool):
        """切换AI助手模式"""
        if self.use_m3_mode != use_m3:
            logger.info(f"正在切换AI助手模式: {'传统模式' if self.use_m3_mode else 'M3编排器'} -> {'M3编排器' if use_m3 else '传统模式'}")
            self.use_m3_mode = use_m3
            # 重新创建Agent实例
            self.agent = create_agent_core_with_llm(use_m3=use_m3)
            if use_m3:
                self.orchestrator = get_orchestrator()
            logger.info(f"AI助手模式已切换为: {'M3编排器' if use_m3 else '传统模式'}")
            return f"✅ 已切换到 {'M3编排器模式' if use_m3 else '传统模式'}"
        return f"当前已经是 {'M3编排器模式' if use_m3 else '传统模式'}"

    async def process_user_message(self, user_input: str, chat_history) -> Tuple[str, List[Tuple[str, str]], str]:
        """
        处理用户消息 - 使用会话状态管理

        Args:
            user_input: 用户输入
            chat_history: 聊天历史

        Returns:
            清空的用户输入、更新后的聊天历史、工具轨迹文本
        """
        if not user_input.strip():
            return "", chat_history, "工具轨迹已清除"

        # 更新活动时间
        self.update_activity()

        # 初始化会话ID（如果还没有）
        if self.session_id is None:
            self.session_id = str(uuid.uuid4())
            logger.info(f"创建新会话: {self.session_id}")

        logger.info(f"收到用户输入 (会话{self.session_id}): {user_input[:100]}{'...' if len(user_input) > 100 else ''}")

        try:
            if self.use_m3_mode and self.orchestrator:
                # 使用M3编排器的会话状态管理
                result = await self.orchestrator.process_message(user_input, self.session_id)

                # 处理结果
                if result.status == "waiting_for_user":
                    # 等待用户回答问题 - 设置session的pending_ask状态
                    from orchestrator import get_session
                    session = get_session(self.session_id)

                    if result.pending_questions:
                        question = result.pending_questions[0]  # 取第一个问题
                        # 推断期望的答案类型
                        expects = "user_input"
                        if "城市" in question or "city" in question.lower():
                            expects = "city"
                        elif "日期" in question or "date" in question.lower():
                            expects = "date"

                        session.set_pending_ask(question, expects)

                        message = f"🤔 {question}\n\n请在输入框中直接回复，我将继续为您处理请求。"
                        chat_history.append((user_input, message))
                        tool_trace_text = f"🕐 等待用户回答问题..."
                    else:
                        chat_history.append((user_input, "等待用户输入..."))
                        tool_trace_text = "🕐 等待用户回答"
                elif result.status == "terminated":
                    # 任务已结束
                    chat_history.append((user_input, result.final_answer or "任务已结束"))
                    tool_trace_text = "✅ 任务已结束"
                elif result.final_answer:
                    # 有最终答案
                    final_message = result.final_answer

                    # 检查是否有文件保存信息
                    if hasattr(result, 'execution_state') and result.execution_state:
                        artifacts = result.execution_state.artifacts
                        file_info = self._extract_file_info(artifacts)
                        if file_info:
                            final_message += f"\n\n📁 **文件已保存**\n{file_info}"

                    chat_history.append((user_input, final_message))
                    tool_trace_text = self._generate_tool_trace(result)
                else:
                    # 其他状态
                    status_msg = f"处理完成 (状态: {result.status})"

                    # 即使失败，也尝试显示文件信息
                    if hasattr(result, 'execution_state') and result.execution_state:
                        artifacts = result.execution_state.artifacts
                        file_info = self._extract_file_info(artifacts)
                        if file_info:
                            status_msg += f"\n\n📁 **文件已保存**\n{file_info}"

                    chat_history.append((user_input, status_msg))
                    tool_trace_text = f"状态: {result.status}"

            else:
                # 使用传统模式（原有逻辑）
                return await self._process_traditional(user_input, chat_history)

        except Exception as e:
            error_msg = f"处理消息时发生错误: {str(e)}"
            logger.error(error_msg, exc_info=True)
            assistant_response = "抱歉，处理您的请求时出现了错误，请稍后重试。"
            chat_history.append((user_input, assistant_response))
            tool_trace_text = "❌ 处理过程中发生错误"

        # 支持多轮对话，不清空输入框
        return None, chat_history, tool_trace_text

    async def _process_traditional(self, user_input: str, chat_history) -> Tuple[str, List[Tuple[str, str]], str]:
        """传统模式处理（向后兼容）"""
        # 检查是否是用户回答ask_user工具的问题
        if hasattr(self.agent, 'pending_ask_user'):
            # 如果有待回答的ask_user问题，先处理用户回答
            answer = user_input.strip()
            logger.info(f"处理用户对ask_user工具的回答: {answer}")

            # 处理用户对ask_user的回答
            original_input = self.agent.pending_ask_user.get('original_input', '')
            question = self.agent.pending_ask_user.get('question', '问题')

            # 清除pending状态
            delattr(self.agent, 'pending_ask_user')

            # 构造包含用户回答的新查询
            enhanced_query = f"{original_input}\n\n用户回答: {answer}"

            # 更新最后一个AI消息，显示用户已回答，然后继续处理
            if chat_history and chat_history[-1][1].startswith("🤔"):
                chat_history[-1] = (f"🤔 {question}", f"✅ 已回答: {answer}\n\n正在继续处理...")

            return await self._process_stream(enhanced_query, chat_history, is_followup=True)

        else:
            # 正常处理用户查询
            # 先显示用户输入，然后使用流式处理
            chat_history.append((user_input, ""))
            return await self._process_stream(user_input, chat_history)

    async def _process_stream(self, user_input: str, chat_history, is_followup: bool = False) -> Tuple[str, List[Tuple[str, str]], str]:
        """
        流式处理用户输入

        Args:
            user_input: 用户输入
            chat_history: 聊天历史（已经包含了用户输入）

        Returns:
            处理后的输入、聊天历史、工具轨迹
        """
        # 流式处理
        full_response = ""
        tool_trace_text = ""
        status_message = ""
        metadata = {}

        # 用户输入已在process_user_message中添加，这里不需要重复添加

        try:
            async for chunk in self.agent.process_stream(user_input):
                if chunk.get("type") == "status":
                    # 状态更新
                    status_message = chunk["message"]
                    # 更新聊天历史中的AI回复，显示推理状态
                    if not full_response:
                        # 如果还没有内容，只显示状态
                        chat_history[-1] = (user_input, f"🔄 {status_message}...")
                    else:
                        # 如果已有内容，在内容后显示状态
                        chat_history[-1] = (user_input, f"{full_response}\n\n🔄 {status_message}...")

                elif chunk.get("type") == "content":
                    # 增量内容
                    full_response += chunk["content"]
                    # 更新聊天历史，移除状态信息以显示纯内容
                    chat_history[-1] = (user_input, full_response)

                elif chunk.get("type") == "tool_result":
                    # 工具执行结果
                    tool_name = chunk["tool_name"]
                    result = chunk["result"]
                    tool_trace_text += f"✅ {tool_name}: {str(result)[:100]}{'...' if len(str(result)) > 100 else ''}\n"

                elif chunk.get("type") == "ask_user":
                    # ask_user工具调用 - 显示输入界面
                    question = chunk["question"]
                    context = chunk["context"]
                    self.agent.pending_ask_user = {
                        'tool_call': chunk["tool_call"],
                        'question': question,
                        'context': context,
                        'original_input': user_input
                    }

                    # 显示需要用户输入的提示
                    message = f"🤔 {question}"
                    if context:
                        message += f"\n\n上下文：{context}"
                    message += "\n\n请在下方输入框中回复，我将继续为您处理请求。"

                    # 替换最后一个条目的AI回复，但保持用户输入不变
                    if chat_history and len(chat_history[-1]) == 2:
                        chat_history[-1] = (chat_history[-1][0], message)

                    # 设置等待用户输入状态
                    break

                elif chunk.get("type") == "final":
                    # 最终结果
                    full_response = chunk["response"]
                    metadata = chunk["metadata"]

                    # 记录统计信息
                    self._log_statistics(metadata)

                    # 获取最终的工具轨迹
                    final_tool_trace = self.format_tool_trace(metadata.get("tool_call_trace", []))
                    if final_tool_trace:
                        tool_trace_text = final_tool_trace

                    # 最终更新聊天历史
                    if is_followup:
                        # followup时更新最后一个消息（应该是"正在处理..."的消息）
                        # 保持原有的显示格式，只更新AI回复部分
                        current_user_part = chat_history[-1][0] if chat_history[-1][0] else f"🤔 {self.agent.pending_ask_user.get('question', '问题') if hasattr(self.agent, 'pending_ask_user') else '用户'}"
                        chat_history[-1] = (current_user_part, full_response)
                    else:
                        # 正常情况下更新用户输入对应的AI回复
                        chat_history[-1] = (user_input, full_response)

                    # 保存对话历史
                    self.save_current_conversation()

                    break

                elif chunk.get("type") == "error":
                    # 错误
                    error_msg = chunk["error"]
                    chat_history[-1] = (user_input, f"❌ 处理出错: {error_msg}")
                    tool_trace_text = "❌ 处理过程中发生错误"
                    break

        except Exception as e:
            logger.error(f"流式处理异常: {e}")
            if not is_followup:
                chat_history[-1] = (user_input, f"❌ 处理出错: {str(e)}")
            else:
                chat_history.append(("", f"❌ 处理出错: {str(e)}"))
            tool_trace_text = "❌ 处理过程中发生错误"

        # 不清空输入框，支持多轮对话
        return None, chat_history, tool_trace_text

    def _log_statistics(self, metadata: Dict[str, Any]):
        """记录统计信息"""
        if "response_time" in metadata:
            logger.info(f"响应时间: {metadata['response_time']:.2f}s")

        if "usage" in metadata and metadata["usage"]:
            usage = metadata["usage"]
            if "total_tokens" in usage:
                logger.info(f"Token使用: {usage['total_tokens']}")
            if "prompt_tokens" in usage:
                logger.info(f"输入Token: {usage['prompt_tokens']}")
            if "completion_tokens" in usage:
                logger.info(f"输出Token: {usage['completion_tokens']}")

    def save_current_conversation(self):
        """保存当前对话到RAG数据库"""
        if not self.chat_history:
            return

        try:
            # 准备对话数据
            conversation_data = {
                "id": self.current_conversation_id or str(uuid.uuid4()),
                "title": self._generate_conversation_title(),
                "content": self._format_conversation_content(),
                "metadata": {
                    "message_count": len(self.chat_history),
                    "total_tokens": sum(meta.get("usage", {}).get("total_tokens", 0)
                                      for meta in self.metadata_history if meta),
                    "mode": "m3" if self.use_m3_mode else "traditional",
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                },
                "raw_history": self.chat_history.copy(),
                "raw_metadata": self.metadata_history.copy()
            }

            # 如果有RAG数据库，调用RAG接口
            if self.rag_store:
                success = self.rag_store.save_conversation(conversation_data)
                if success:
                    logger.info(f"对话已保存到RAG数据库: {conversation_data['id']}")
                else:
                    logger.error("保存对话到RAG数据库失败")
            else:
                # 临时存储在内存中
                self.temp_conversation_cache[conversation_data["id"]] = conversation_data
                logger.info(f"对话已临时保存到内存缓存: {conversation_data['id']}")

            if not self.current_conversation_id:
                self.current_conversation_id = conversation_data["id"]

        except Exception as e:
            logger.error(f"保存对话失败: {e}")

    def _format_conversation_content(self) -> str:
        """格式化对话内容为适合RAG存储的文本"""
        content_parts = []
        for i, (user_msg, ai_msg) in enumerate(self.chat_history):
            content_parts.append(f"用户: {user_msg}")
            if ai_msg:
                content_parts.append(f"助手: {ai_msg}")
        return "\n\n".join(content_parts)

    def _generate_conversation_title(self) -> str:
        """根据第一条用户消息生成对话标题"""
        if self.chat_history:
            first_user_msg = self.chat_history[0][0]
            # 截取前20个字符作为标题
            title = first_user_msg[:20]
            if len(first_user_msg) > 20:
                title += "..."
            return title
        return "新对话"

    def new_conversation(self, chat_history) -> Tuple[List[Tuple[str, str]], str, str]:
        """开始新对话"""
        logger.info("开始新对话")

        # 保存当前对话
        self.save_current_conversation()

        # 重置当前对话
        self.chat_history = []
        self.metadata_history = []
        self.current_conversation_id = None

        # 清空pending状态
        if hasattr(self.agent, 'pending_ask_user'):
            delattr(self.agent, 'pending_ask_user')

        return None, [], "工具轨迹已清除"

    def load_conversation(self, conversation_id: str) -> Tuple[List[Tuple[str, str]], str]:
        """从RAG数据库加载指定的对话"""
        try:
            if self.rag_store:
                # 从RAG数据库加载
                conversation_data = self.rag_store.load_conversation(conversation_id)
                if conversation_data:
                    self.current_conversation_id = conversation_id
                    self.chat_history = conversation_data.get("raw_history", [])
                    self.metadata_history = conversation_data.get("raw_metadata", [])
                    title = conversation_data.get("title", "未知对话")
                    return self.chat_history, f"已加载对话: {title}"
            else:
                # 从临时缓存加载
                if conversation_id in self.temp_conversation_cache:
                    conv_data = self.temp_conversation_cache[conversation_id]
                    self.current_conversation_id = conversation_id
                    self.chat_history = conv_data.get("raw_history", [])
                    self.metadata_history = conv_data.get("raw_metadata", [])
                    return self.chat_history, f"已加载对话: {conv_data.get('title', '未知对话')}"

            return [], "未找到指定对话"

        except Exception as e:
            logger.error(f"加载对话失败: {e}")
            return [], f"加载对话失败: {e}"

    def delete_conversation(self, conversation_id: str) -> bool:
        """从RAG数据库删除指定的对话"""
        try:
            if self.rag_store:
                # 从RAG数据库删除
                return self.rag_store.delete_conversation(conversation_id)
            else:
                # 从临时缓存删除
                if conversation_id in self.temp_conversation_cache:
                    del self.temp_conversation_cache[conversation_id]
                    if self.current_conversation_id == conversation_id:
                        self.current_conversation_id = None
                        self.chat_history = []
                        self.metadata_history = []
                    return True
            return False

        except Exception as e:
            logger.error(f"删除对话失败: {e}")
            return False

    def get_conversation_list(self) -> List[Dict[str, Any]]:
        """从RAG数据库获取对话列表"""
        try:
            if self.rag_store:
                # 从RAG数据库获取
                conversations = self.rag_store.list_conversations()
                return conversations or []
            else:
                # 从临时缓存获取
                return [
                    {
                        "id": conv_id,
                        "title": conv_data.get("title", "未知对话"),
                        "created_at": conv_data["metadata"].get("created_at", ""),
                        "updated_at": conv_data["metadata"].get("updated_at", ""),
                        "message_count": conv_data["metadata"].get("message_count", 0)
                    }
                    for conv_id, conv_data in self.temp_conversation_cache.items()
                ]

        except Exception as e:
            logger.error(f"获取对话列表失败: {e}")
            return []

    def search_conversations(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """搜索相关对话（预留RAG搜索接口）"""
        try:
            if self.rag_store:
                # 使用RAG数据库搜索
                return self.rag_store.search_conversations(query, limit)
            else:
                # 临时实现：简单文本匹配
                results = []
                query_lower = query.lower()
                for conv_id, conv_data in self.temp_conversation_cache.items():
                    content = conv_data.get("content", "").lower()
                    if query_lower in content:
                        results.append({
                            "id": conv_id,
                            "title": conv_data.get("title", "未知对话"),
                            "content_snippet": content[:200] + "..." if len(content) > 200 else content,
                            "score": 1.0  # 临时分数
                        })
                        if len(results) >= limit:
                            break
                return results

        except Exception as e:
            logger.error(f"搜索对话失败: {e}")
            return []

    def clear_history(self, chat_history) -> Tuple[List[Tuple[str, str]], str, str]:
        """清除聊天历史（保留在历史记录中）"""
        logger.info("清除当前聊天历史")
        self.chat_history = []
        self.metadata_history = []
        return [], "当前聊天历史已清除", "工具轨迹已清除"

    def get_system_info(self) -> str:
        """获取系统信息"""
        provider_info = f"当前模型提供商: {self.config.model_provider}"
        if hasattr(self.config, 'deepseek_model'):
            provider_info += f" ({self.config.deepseek_model})"
        mode_info = f"AI助手模式: {'M3编排器' if self.use_m3_mode else '传统模式'}"
        rag_status = f"RAG功能: {'启用' if self.config.rag_enabled else '禁用'}"
        tools_status = f"工具功能: {'启用' if self.config.tools_enabled else '禁用'} ({len(self.agent.tools) if hasattr(self, 'agent') else 0}个工具)"
        log_level = f"日志级别: {self.config.log_level}"

        return f"{provider_info}\n{mode_info}\n{rag_status}\n{tools_status}\n{log_level}"

    def format_tool_trace(self, tool_trace: list, orchestrator_trace: dict = None) -> str:
        """格式化工具调用轨迹"""
        if not tool_trace and not orchestrator_trace:
            return "本次对话未使用任何工具"

        trace_lines = ["🛠️ 工具调用轨迹:"]

        # 如果有编排器轨迹，优先显示阶段信息
        if orchestrator_trace:
            phases = orchestrator_trace.get("phases", [])
            for phase in phases:
                phase_name = phase.get("phase", "UNKNOWN")
                duration = phase.get("duration", 0)
                status = phase.get("status", "completed")

                phase_icon = {
                    "PLAN": "📋",
                    "ACT": "⚡",
                    "JUDGE": "⚖️"
                }.get(phase_name, "❓")

                status_icon = "✅" if status == "completed" else "❌" if status == "failed" else "⏳"
                trace_lines.append(f"{phase_icon} {phase_name}阶段 {status_icon} ({duration:.2f}s)")

                # 显示该阶段的工具调用
                tools = phase.get("tools", [])
                for tool in tools:
                    tool_name = tool.get("name", "未知工具")
                    args = tool.get("args", {})
                    summary = tool.get("summary", "")
                    latency = tool.get("latency", 0)

                    # 格式化参数显示
                    args_str = ", ".join(f"{k}={v}" for k, v in list(args.items())[:3])  # 只显示前3个参数
                    if len(args) > 3:
                        args_str += "..."

                    trace_lines.append(f"  └─ {tool_name}({args_str}) → {summary} ({latency:.2f}s)")

        # 兼容旧的tool_trace格式
        elif tool_trace:
            for i, trace in enumerate(tool_trace, 1):
                tool_name = trace.get("tool_name", "未知工具")
                execution_time = trace.get("execution_time", 0)
                success = not trace.get("error")

                status_icon = "✅" if success else "❌"
                trace_lines.append(f"{i}. {status_icon} {tool_name} ({execution_time:.2f}s)")

                if trace.get("error"):
                    trace_lines.append(f"   错误: {trace['error'][:100]}...")

        return "\n".join(trace_lines)

    def _generate_tool_trace(self, result) -> str:
        """生成工具轨迹文本"""
        if not hasattr(result, 'execution_state') or not result.execution_state:
            return "本次对话未使用任何工具"

        artifacts = result.execution_state.artifacts
        if not artifacts:
            return "本次对话未使用任何工具"

        trace_lines = ["🛠️ 工具调用轨迹:"]
        tool_count = 0

        for key, value in artifacts.items():
            if key.startswith(('user_', 'system_')):
                continue  # 跳过用户输入和系统信息

            tool_count += 1
            if isinstance(value, dict) and 'ok' in value:
                # StandardToolResult格式
                status = "✅" if value.get('ok') else "❌"
                tool_name = value.get('meta', {}).get('source', key)
                latency = value.get('meta', {}).get('latency_ms', 0)
                trace_lines.append(f"{tool_count}. {status} {tool_name} ({latency:.0f}ms)")
            else:
                # 其他格式
                trace_lines.append(f"{tool_count}. ✅ {key}")

        if tool_count == 0:
            return "本次对话未使用任何工具"

        return "\n".join(trace_lines)

    def _extract_file_info(self, artifacts: Dict[str, Any]) -> str:
        """从artifacts中提取文件保存信息"""
        file_info_parts = []

        for key, value in artifacts.items():
            if isinstance(value, dict) and 'ok' in value and value.get('ok'):
                # StandardToolResult格式
                meta = value.get('meta', {})
                if meta.get('source') == 'fs_write':
                    # 文件写入工具的结果
                    data = value.get('data', {})
                    if data and 'path_abs' in data:
                        path_abs = data['path_abs']
                        bytes_written = data.get('bytes', 0)

                        # 尝试转换为用户友好的路径
                        try:
                            from pathlib import Path
                            path_obj = Path(path_abs)
                            home = Path.home()

                            # 相对于用户主目录的路径
                            try:
                                relative_path = path_obj.relative_to(home)
                                display_path = f"~/{relative_path}"
                            except ValueError:
                                display_path = str(path_abs)

                        except Exception:
                            display_path = str(path_abs)

                        file_info_parts.append(f"📄 {display_path}")
                        if bytes_written > 0:
                            file_info_parts.append(f"   大小: {bytes_written} 字节")

        return "\n".join(file_info_parts) if file_info_parts else ""


def create_gradio_interface(ui: ChatUI = None) -> gr.Blocks:
    """创建Gradio界面"""

    if ui is None:
        ui = ChatUI()

    with gr.Blocks(
        title="AI个人助理",
        theme=gr.themes.Soft(),
        css="""
        .gradio-container {
            max-width: 800px;
            margin: auto;
        }
        .chatbot {
            height: 500px;
        }
        """
    ) as interface:

        gr.Markdown("# 🤖 AI个人助理")
        gr.Markdown("*基于大语言模型的个人助手，目前支持基础对话功能*")

        # 创建页签
        with gr.Tabs():
            # 聊天页签
            with gr.TabItem("💬 聊天"):
                # 系统信息显示
                with gr.Accordion("系统信息", open=False):
                    system_info = gr.Textbox(
                        value=ui.get_system_info(),
                        interactive=False,
                        lines=4,
                        label="当前配置"
                    )

                    # 模式切换
                    with gr.Row():
                        mode_selector = gr.Radio(
                            choices=["传统模式", "M3编排器模式"],
                            value="传统模式",
                            label="AI助手模式",
                            interactive=True
                        )
                        mode_status = gr.Textbox(
                            value="当前: 传统模式",
                            interactive=False,
                            label="切换状态",
                            scale=2
                        )

                    # 绑定模式切换事件
                    mode_selector.change(
                        fn=lambda x: ui.switch_mode(x == "M3编排器模式"),
                        inputs=[mode_selector],
                        outputs=[mode_status]
                    )

                # 聊天界面
                chatbot = gr.Chatbot(
                    height=500,
                    show_label=False,
                    container=True
                )

                # 工具轨迹面板
                with gr.Accordion("🛠️ 工具调用轨迹", open=False):
                    tool_trace_display = gr.Textbox(
                        value="本次对话未使用任何工具",
                        interactive=False,
                        lines=8,
                        label="工具调用详情",
                        show_label=False
                    )

                # 输入框
                with gr.Row():
                    user_input = gr.Textbox(
                        placeholder="请输入您的问题...",
                        show_label=False,
                        container=False,
                        scale=8
                    )
                    submit_btn = gr.Button("发送", scale=1, variant="primary")
                    new_conv_btn = gr.Button("新对话", scale=1)

                # 绑定事件
                submit_btn.click(
                    ui.process_user_message,
                    inputs=[user_input, chatbot],
                    outputs=[user_input, chatbot, tool_trace_display],
                    concurrency_limit=1
                )

                user_input.submit(
                    ui.process_user_message,
                    inputs=[user_input, chatbot],
                    outputs=[user_input, chatbot, tool_trace_display],
                    concurrency_limit=1
                )

                new_conv_btn.click(
                    ui.new_conversation,
                    inputs=[chatbot],
                    outputs=[chatbot, user_input, tool_trace_display]
                )

            # 历史聊天页签
            with gr.TabItem("📚 历史记录"):
                gr.Markdown("### 对话历史记录")
                gr.Markdown("*基于日期时间存储，支持RAG搜索（待实现）*")

                # 搜索框
                search_input = gr.Textbox(
                    placeholder="搜索对话内容...",
                    label="搜索",
                    show_label=False
                )

                # 对话列表
                conversation_list = gr.Dataframe(
                    headers=["标题", "消息数", "创建时间", "更新时间"],
                    datatype=["str", "number", "str", "str"],
                    interactive=False,
                    label="对话列表"
                )

                # 操作按钮
                with gr.Row():
                    load_btn = gr.Button("加载选中对话", variant="secondary")
                    delete_btn = gr.Button("删除选中对话", variant="stop")
                    refresh_btn = gr.Button("刷新列表", variant="secondary")

                # 绑定事件
                def update_conversation_list():
                    """更新对话列表"""
                    conversations = ui.get_conversation_list()
                    # 转换为DataFrame格式
                    df_data = []
                    for conv in conversations:
                        df_data.append([
                            conv.get("title", "未知"),
                            conv.get("message_count", 0),
                            conv.get("created_at", "")[:19],  # 只显示到分钟
                            conv.get("updated_at", "")[:19]
                        ])
                    return df_data

                refresh_btn.click(
                    fn=update_conversation_list,
                    outputs=[conversation_list]
                )

                # 页面加载时自动刷新列表
                conversation_list.value = update_conversation_list()

        # 页脚信息
        gr.Markdown("---")
        gr.Markdown("*提示：直接在输入框中输入问题并按Enter，或点击发送按钮*")

    return interface


def main():
    """主函数 - 创建Gradio界面并启动服务器"""
    logger.info("启动Gradio UI...")

    try:
        # 创建UI实例
        ui = ChatUI()
        interface = create_gradio_interface(ui)

        # 启动心跳机制
        ui.start_heartbeat()

        # 启用队列以提高稳定性
        interface.queue(max_size=20, api_open=False)

        # 启动服务器
        interface.launch(
            server_name="0.0.0.0",
            server_port=7860,
            share=False,
            show_error=True,
            inbrowser=True,
            max_threads=4,
            auth=None,
        )

        logger.info("Gradio UI启动成功，心跳机制已启用")

    except KeyboardInterrupt:
        logger.info("收到中断信号，正在关闭...")
        # 停止心跳机制
        if 'ui' in locals():
            ui.stop_heartbeat()
    except Exception as e:
        logger.error(f"启动Gradio UI时发生错误: {str(e)}", exc_info=True)
        # 停止心跳机制
        if 'ui' in locals():
            ui.stop_heartbeat()
        raise
    finally:
        # 确保心跳机制被停止
        if 'ui' in locals():
            ui.stop_heartbeat()


def create_ui():
    """创建Gradio界面（不启动服务器）"""
    logger.info("创建Gradio UI界面...")

    # 创建UI实例
    ui = ChatUI()
    interface = create_gradio_interface(ui)

    # 启动心跳机制
    ui.start_heartbeat()

    # 启用队列以提高稳定性
    interface.queue(max_size=20, api_open=False)

    logger.info("Gradio UI界面创建完成，可调用 interface.launch() 启动服务器")
    return interface


if __name__ == "__main__":
    main()
