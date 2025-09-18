"""
Chainlit UI 入口 - 真·流式 + 事件分流 + AskUser 续跑 + 本地 RAG
实现极简但实用的 AgentFlow 前端
"""
import os
import asyncio
import anyio
import chainlit as cl
from typing import Dict, Any, Optional
import uuid
from asyncio import Queue

# AgentFlow 相关导入
from agent_core import create_agent_core_with_llm
from orchestrator import get_session
from config import get_config
from router import route_query, QueryType, explain_routing

# 全局变量
agent_core = None
config = None


@cl.on_chat_start
async def on_chat_start():
    """聊天开始时的初始化"""
    global agent_core, config

    # 初始化配置和Agent
    config = get_config()
    agent_core = create_agent_core_with_llm(use_m3=True)

    # 创建会话ID
    session_id = str(uuid.uuid4())
    cl.user_session.set("session_id", session_id)

    # 初始化侧栏状态
    cl.user_session.set("sidebar_logs", [])

    # 初始化等待用户输入状态
    cl.user_session.set("waiting_for_user_input", False)

    # 发送欢迎消息
    await cl.Message(content="🤖 AgentFlow 已启动！支持真·流式响应和会话续跑。").send()


@cl.on_message
async def on_message(message: cl.Message):
    """处理用户消息 - 支持真·流式、智能分流和AskUser续跑"""
    global agent_core

    if not agent_core:
        await cl.Message(content="❌ Agent 未初始化，请刷新页面重试").send()
        return

    session_id = cl.user_session.get("session_id")
    if not session_id:
        await cl.Message(content="❌ 会话ID丢失，请刷新页面").send()
        return

    # 立即显示用户输入
    user_msg = cl.Message(content=message.content, author="用户")
    await user_msg.send()

    # 检查是否有pending_ask（后端状态）
    session = get_session(session_id)
    if session.has_pending_ask():
        # 这是对之前问题的回答，直接续跑任务
        await handle_resume_with_answer(message.content, session_id)
        return

    # 检查前端等待状态
    is_waiting = cl.user_session.get("waiting_for_user_input", False)
    if is_waiting:
        # 这是对之前问题的回答
        await handle_resume_with_answer(message.content, session_id)
        cl.user_session.set("waiting_for_user_input", False)
        return

    # 智能路由：区分简单问答和复杂编排
    query_type, routing_metadata = route_query(message.content)

    routing_explanation = explain_routing(query_type, routing_metadata)

    # 显示路由决策（可选）
    routing_msg = cl.Message(
        content=f"🔀 **路由决策**: {query_type.value}模式\n{routing_explanation}",
        author="系统"
    )
    await routing_msg.send()

    if query_type == QueryType.SIMPLE_CHAT:
        # 简单问答：直接用Chat模型
        await handle_simple_chat(message.content, session_id)
    else:
        # 复杂编排：走Planner→Executor→Judge
        await handle_complex_plan(message.content, session_id)


async def handle_resume_with_answer(user_answer: str, session_id: str):
    """处理用户对pending_ask的回答 - 会话续跑"""
    from orchestrator import get_session
    session = get_session(session_id)

    if not session.has_pending_ask():
        await cl.Message(content="❌ 没有等待回答的问题").send()
        return

    pending_ask = session.pending_ask

    # 显示用户回答
    answer_msg = cl.Message(
        content=f"✅ **回答了问题**: {user_answer}\n\n🔄 正在继续执行任务...",
        author="系统"
    )
    await answer_msg.send()

    # 清除pending状态并续跑
    session.clear_pending_ask()

    # 创建新的orchestrator实例进行续跑
    from orchestrator import Orchestrator
    orchestrator = Orchestrator()

    try:
        # 强制重新规划并执行
        result = await orchestrator._force_replan(session.active_task)

        if result.status == "ask_user" and result.pending_questions:
            # 又产生了新问题
            question = result.pending_questions[0]
            await cl.Message(content=f"🤔 {question}", author="助手").send()
            # 设置新的pending_ask
            session.set_pending_ask(question, "answer")
        elif result.final_answer:
            # 完成任务
            await cl.Message(content=result.final_answer, author="助手").send()
        else:
            await cl.Message(content=f"任务状态: {result.status}", author="助手").send()

    except Exception as e:
        await cl.Message(content=f"❌ 续跑失败: {str(e)}", author="助手").send()


async def handle_simple_chat(user_input: str, session_id: str):
    """处理简单问答 - 直接用Chat模型"""
    global agent_core

    try:
        # 创建空的assistant消息用于流式输出
        assistant_msg = await cl.Message(content="", author="助手").send()

        # 调用agent的简单chat方法（这里假设agent_core有对应的方法）
        # 如果没有，需要添加一个简单的chat接口
        response = await agent_core.simple_chat(user_input, context={"session_id": session_id})

        # 流式输出响应
        if isinstance(response, str):
            # 如果是字符串，直接输出
            await assistant_msg.stream_token(response)
        else:
            # 如果是流式响应，逐token输出
            async for token in response:
                await assistant_msg.stream_token(token)
                await asyncio.sleep(0)  # 让事件循环有机会处理

        # 完成流式输出
        await assistant_msg.update()

    except Exception as e:
        error_msg = await cl.Message(content=f"❌ 处理失败: {str(e)}", author="助手").send()


async def handle_complex_plan(user_input: str, session_id: str):
    """处理复杂编排任务 - 真·流式 + 事件分流"""
    global agent_core

    try:
        # 创建空的assistant消息用于流式输出
        assistant_msg = await cl.Message(content="", author="助手").send()

        # 用于收集侧栏日志
        sidebar_logs = []

        def sync_event_generator():
            """同步事件生成器包装器"""
            # 这里假设agent_core._process_with_m3_stream返回同步生成器
            # 如果是异步的，需要相应调整
            for event in agent_core._process_with_m3_stream(user_input, context={"session_id": session_id}):
                yield event

        # 使用anyio.to_thread处理同步生成器，避免阻塞事件循环
        async for event in anyio.to_thread.run_sync(sync_event_generator):
            event_type = event.get("type", "")
            message = event.get("message", "")

            if event_type == "assistant_content":
                # 真·流式：逐token输出
                content_delta = event.get("content", "")
                if content_delta:
                    await assistant_msg.stream_token(content_delta)
                    await asyncio.sleep(0)  # 让事件循环flush

            elif event_type in ["status", "tool_trace", "debug"]:
                # 事件分流：进入侧栏
                if message:
                    log_entry = f"🔄 {message}"
                    sidebar_logs.append(log_entry)

                    # 创建侧栏消息
                    await cl.Message(
                        content=log_entry,
                        author="系统日志"
                    ).send()

            elif event_type == "ask_user":
                # AskUser优化：发问即返回，下条消息resume
                question = event.get("question", "请提供更多信息")
                context_info = event.get("context", "")

                # 显示问题并设置等待状态
                ask_msg = await cl.Message(
                    content=f"🤔 {question}\n\n请直接回复，我将继续处理。",
                    author="助手"
                ).send()

                # 设置前端等待状态
                cl.user_session.set("waiting_for_user_input", True)

                # 设置后端pending_ask状态
                session = get_session(session_id)
                session.set_pending_ask(question, "answer")

                # 立即返回，不继续处理（避免超时）
                return

            elif event_type == "error":
                # 错误处理
                error_msg = event.get("message", "未知错误")
                await assistant_msg.stream_token(f"\n\n❌ {error_msg}")
                break

        # 完成流式输出
        await assistant_msg.update()

        # 添加完成标记到侧栏
        completion_log = "✅ 处理完成"
        await cl.Message(content=completion_log, author="系统日志").send()

    except Exception as e:
        error_msg = await cl.Message(content=f"❌ 处理失败: {str(e)}", author="助手").send()


@cl.on_stop
def on_stop():
    """连接停止时的清理"""
    session_id = cl.user_session.get("session_id")
    if session_id:
        # 可以在这里清理会话状态
        pass


@cl.on_chat_end
def on_chat_end():
    """聊天结束时的清理"""
    session_id = cl.user_session.get("session_id")
    if session_id:
        # 清理会话数据
        pass


# 自定义CSS样式（可选，用于优化显示效果）
custom_css = """
.chat-message {
    margin-bottom: 1rem;
}

.chat-message.user {
    background-color: #e3f2fd;
}

.chat-message.assistant {
    background-color: #f5f5f5;
}

.system-log {
    font-size: 0.9em;
    color: #666;
    font-style: italic;
}
"""


if __name__ == "__main__":
    # 设置自定义CSS
    cl.set_css(custom_css)

    # 启动Chainlit应用
    # 注意：实际运行时使用命令：chainlit run ui_chainlit.py -w
