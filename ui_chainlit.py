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

    # 创建会话ID - 使用session管理器
    import sys
    import os
    sys.path.append(os.path.dirname(__file__))
    from session_manager import session_manager
    from utils.telemetry import get_telemetry_logger, TelemetryEvent, TelemetryStage
    session_id = session_manager.get_or_create_session_id(cl.user_session)

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

    # 确保路径设置和导入
    import sys
    import os
    if os.path.dirname(__file__) not in sys.path:
        sys.path.append(os.path.dirname(__file__))

    from session_manager import session_manager
    from utils.telemetry import get_telemetry_logger, TelemetryEvent, TelemetryStage

    session_id = session_manager.get_or_create_session_id(cl.user_session)

    # 立即显示用户输入
    user_msg = cl.Message(content=message.content, author="用户")
    await user_msg.send()

    # 获取session并记录用户消息到对话历史
    session = get_session(session_id)
    session.add_message("user", message.content)

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
        # 简单问答：直接用快速Agent
        await handle_simple_chat(routing_metadata.get("clean_query", message.content), session_id)
    else:
        # 复杂编排：走Planner→Executor→Judge
        await handle_complex_plan(routing_metadata.get("clean_query", message.content), session_id)


async def handle_resume_with_answer(user_answer: str, session_id: str):
    """处理用户对pending_ask的回答 - 会话续跑"""
    print(f"[DEBUG] UI进入续跑函数 - session_id='{session_id}', user_answer='{user_answer}'")
    global agent_core
    from orchestrator import get_session
    from session_manager import session_manager
    from utils.telemetry import get_telemetry_logger, TelemetryEvent, TelemetryStage
    session = get_session(session_id)
    print(f"[DEBUG] UI获取session完成，检查是否有pending_ask: {session.has_pending_ask()}")

    if not session.has_pending_ask():
        await cl.Message(content="❌ 没有等待回答的问题").send()
        return

    # 显示用户回答
    answer_msg = cl.Message(
        content=f"✅ **回答了问题**: {user_answer}\n\n🔄 正在继续执行任务...",
        author="系统"
    )
    await answer_msg.send()

    # 记录用户回答到对话历史
    session.add_message("user", f"回答了问题: {user_answer}")

    # 验证ask_id一致性
    current_ask_id = cl.user_session.get("current_ask_id", "")
    print(f"[DEBUG] UI校验ask_id一致性: current_ask_id='{current_ask_id}', session.pending_ask.ask_id='{session.pending_ask.ask_id if session.pending_ask else 'NONE'}'")

    if not session_manager.validate_ask_id_consistency(session, current_ask_id):
        print(f"[DEBUG] AskID不一致! 期望: '{session.pending_ask.ask_id if session.pending_ask else 'NONE'}', 实际: '{current_ask_id}'")
        # 记录session不匹配事件
        from utils.telemetry import log_session_mismatch
        expected_ask_id = session.pending_ask.ask_id if session.pending_ask else ""
        log_session_mismatch(
            session_id=session_id,
            expected_session_id=session_id,
            actual_session_id=session_id,
            expected_ask_id=expected_ask_id,
            actual_ask_id=current_ask_id
        )
        await cl.Message(content=f"❌ AskID不匹配或状态异常，请重新开始任务", author="系统").send()
        return

    # 记录ask_user_resume事件
    if current_ask_id:
        from utils.telemetry import log_ask_user_resume
        # 获取step_id和active_task_id用于三元组日志
        step_id = ""
        active_task_id = ""
        if session.pending_ask:
            step_id = getattr(session.pending_ask, 'step_id', '')
        log_ask_user_resume(
            session_id=session_id,
            ask_id=current_ask_id,
            answer=user_answer,
            step_id=step_id,
            active_task_id=active_task_id
        )

    # 发送ask_user_close事件
    if current_ask_id:
        # 这里可以发送ask_user_close事件，但由于我们已经修改了协议，这里先跳过
        pass

    # 清除pending状态
    session.clear_pending_ask()

    # 清除前端状态
    session_manager.cleanup_session_state(cl.user_session)

    try:
        # 调试信息：检查session状态
        print(f"[DEBUG] 续跑开始 - session_id: {session_id}")
        print(f"[DEBUG] session.active_task: {session.active_task}")
        print(f"[DEBUG] session.pending_ask: {session.pending_ask}")
        print(f"[DEBUG] session id: {id(session)}")
        print(f"[DEBUG] session type: {type(session)}")

        # 检查全局会话存储
        from orchestrator.orchestrator import _sessions
        print(f"[DEBUG] 全局存储中的session数量: {len(_sessions)}")
        print(f"[DEBUG] session_id在全局存储中: {session_id in _sessions}")

        if session_id in _sessions:
            global_session = _sessions[session_id]
            print(f"[DEBUG] 全局session.active_task: {global_session.active_task}")
            print(f"[DEBUG] 全局session.pending_ask: {global_session.pending_ask}")

        # 确保session有active_task状态
        if not session.active_task:
            # 尝试从全局会话存储中恢复
            if session_id in _sessions:
                global_session = _sessions[session_id]
                if global_session.active_task:
                    session.active_task = global_session.active_task
                    print(f"[DEBUG] 从全局存储恢复active_task成功")
                    print(f"[DEBUG] 恢复的active_task: {session.active_task}")
                    print(f"[DEBUG] 恢复的plan: {session.active_task.plan}")
                    print(f"[DEBUG] 恢复的execution_state: {session.active_task.execution_state}")
                else:
                    print(f"[DEBUG] 全局存储中也没有active_task")

            if not session.active_task:
                await cl.Message(content="❌ 会话状态丢失，请重新开始任务", author="助手").send()
                return

        # 将用户答案设置到active_task的execution_state中
        if session.active_task and session.active_task.execution_state:
            # 查找ask_user_pending并设置答案
            ask_user_pending = session.active_task.execution_state.get_artifact("ask_user_pending")
            if ask_user_pending and isinstance(ask_user_pending, dict):
                # 根据expects字段确定正确的output_key
                expects = ask_user_pending.get("expects", "answer")
                if expects == "city":
                    output_key = "user_city"
                elif expects == "date":
                    output_key = "user_date"
                else:
                    output_key = ask_user_pending.get("output_key", "user_answer")

                session.active_task.execution_state.set_artifact(output_key, user_answer)
                # 清除pending状态
                session.active_task.execution_state.set_artifact("ask_user_pending", None)
                print(f"[DEBUG] 在UI层设置用户答案: {output_key} = {user_answer}")

                # 调试：打印所有artifacts
                all_artifacts = session.active_task.execution_state.artifacts
                print(f"[DEBUG] 当前execution_state artifacts: {list(all_artifacts.keys())}")
                for k, v in all_artifacts.items():
                    print(f"[DEBUG]   {k}: {v}")
            else:
                print(f"[DEBUG] ask_user_pending not found or not dict: {ask_user_pending}")

                # 如果没有ask_user_pending，尝试从pending_ask中推断output_key
                if session.pending_ask and hasattr(session.pending_ask, 'expects'):
                    # 根据问题类型推断output_key
                    question = session.pending_ask.question.lower()
                    if "城市" in question or "city" in question:
                        output_key = "user_location"
                    elif "日期" in question or "时间" in question or "date" in question or "time" in question:
                        output_key = "user_date"
                    else:
                        output_key = "user_answer"

                    session.active_task.execution_state.set_artifact(output_key, user_answer)
                    print(f"[DEBUG] 从问题推断output_key: {output_key} = {user_answer}")
        else:
            print(f"[DEBUG] session.active_task或execution_state is None")

        # 使用agent_core继续处理，传递包含active_task的上下文
        context = {
            "session_id": session_id,
            "user_answer": user_answer,
            "resume_task": True,  # 标记这是续跑场景
            "pending_question": session.pending_ask.question if session.pending_ask else None
        }

        # 创建新的assistant消息用于流式输出
        assistant_msg = await cl.Message(content="", author="助手").send()

        # 用于收集侧栏日志
        sidebar_logs = []
        # 累积assistant_content
        full_content = ""
        # token计数用于调试
        token_count = 0

        # 使用agent_core的流式处理方法继续执行（传递session的active_task）
        async for event in agent_core._process_with_m3_stream("", context=context):
            event_type = event.get("type", "")
            payload = event.get("payload", {})

            if event_type == "assistant_content":
                # 真·流式：逐token输出到聊天区域
                content_delta = payload.get("delta", "")
                if content_delta:
                    await assistant_msg.stream_token(content_delta)
                    full_content += content_delta  # 累积内容
                    token_count += 1  # 计数token
                    if token_count % 10 == 0:  # 每10个token打印一次日志
                        print(f"[DEBUG] UI流式token计数: {token_count}")
                    await asyncio.sleep(0)  # 让事件循环flush

            elif event_type in ["status", "tool_trace", "debug"]:
                # 事件分流：进入侧栏
                message = payload.get("message", "")
                if message:
                    log_entry = f"🔄 {message}"
                    sidebar_logs.append(log_entry)

                    # 创建侧栏消息
                    await cl.Message(
                        content=log_entry,
                        author="系统日志"
                    ).send()

            elif event_type == "ask_user_open":
                # 如果又有新问题，设置新的pending状态
                ask_id = payload.get("ask_id", "")
                question = payload.get("question", "请提供更多信息")
                print(f"[DEBUG] UI收到ask_user_open事件 - ask_id='{ask_id}', question='{question}'")

                # 发送问句消息给用户
                ask_msg = await cl.Message(
                    content=f"🤔 {question}\n\n请直接回复，我将继续处理。",
                    author="助手"
                ).send()
                print(f"[DEBUG] UI发送问句消息完成")

                # 设置pending状态
                session.set_pending_ask(question, ask_id)
                cl.user_session.set("waiting_for_user_input", True)
                cl.user_session.set("current_ask_id", ask_id)

                print(f"[DEBUG] UI设置pending状态完成，准备return结束本轮")
                return

            elif event_type == "final_answer":
                # 最终答案
                answer = payload.get("answer", "")
                if answer:
                    await assistant_msg.stream_token(answer)
                    full_content += answer

            elif event_type == "error":
                # 错误处理
                error_code = payload.get("code", "UNKNOWN")
                error_msg = payload.get("message", "未知错误")
                await assistant_msg.stream_token(f"\n\n❌ {error_msg}")
                full_content += f"\n\n❌ {error_msg}"  # 累积错误内容
                break

        # 完成流式输出
        # 完成流式输出 - 最后一次update()确保消息完成状态
        await assistant_msg.update()
        print(f"[DEBUG] UI流式输出完成，总token数: {token_count}")

        # 添加完成标记到侧栏
        completion_log = "✅ 任务继续完成"
        await cl.Message(content=completion_log, author="系统日志").send()

        # 记录助手回复到对话历史
        session = get_session(session_id)
        if full_content:
            session.add_message("assistant", full_content)

    except Exception as e:
        # 确保token_count在异常情况下也有默认值
        token_count = 0
        error_msg = await cl.Message(content=f"❌ 续跑失败: {str(e)}", author="助手").send()

        # 记录错误消息到对话历史
        try:
            session.add_message("assistant", f"❌ 续跑失败: {str(e)}")
        except:
            pass


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
        # 完成流式输出 - 最后一次update()确保消息完成状态
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
        # 累积assistant_content
        full_content = ""
        # token计数用于调试
        token_count = 0

        # 正确处理异步生成器 - agent_core._process_with_m3_stream是async def
        async for event in agent_core._process_with_m3_stream(user_input, context={"session_id": session_id}):
            event_type = event.get("type", "")
            payload = event.get("payload", {})

            if event_type == "assistant_content":
                # 真·流式：逐token输出到聊天区域
                content_delta = payload.get("delta", "")
                if content_delta:
                    await assistant_msg.stream_token(content_delta)
                    full_content += content_delta  # 累积内容
                    token_count += 1  # 计数token
                    if token_count % 10 == 0:  # 每10个token打印一次日志
                        print(f"[DEBUG] UI流式token计数: {token_count}")
                    await asyncio.sleep(0)  # 让事件循环flush

            elif event_type in ["status", "tool_trace", "debug"]:
                # 事件分流：进入侧栏
                message = payload.get("message", "")
                if message:
                    log_entry = f"🔄 {message}"
                    sidebar_logs.append(log_entry)

                    # 创建侧栏消息
                    await cl.Message(
                        content=log_entry,
                        author="系统日志"
                    ).send()

            elif event_type == "ask_user_open":
                # AskUser优化：发问即返回，下条消息resume
                ask_id = payload.get("ask_id", "")
                question = payload.get("question", "请提供更多信息")

                # 显示问题并设置等待状态
                ask_msg = await cl.Message(
                    content=f"🤔 {question}\n\n请直接回复，我将继续处理。",
                    author="助手"
                ).send()

                # 设置前端等待状态和ask_id
                cl.user_session.set("waiting_for_user_input", True)
                cl.user_session.set("current_ask_id", ask_id)

                # 设置后端pending_ask状态
                session = get_session(session_id)
                session.set_pending_ask(question, ask_id)

                # 立即返回，不继续处理（避免超时）
                return

            elif event_type == "final_answer":
                # 最终答案
                answer = payload.get("answer", "")
                if answer:
                    await assistant_msg.stream_token(answer)
                    full_content += answer

            elif event_type == "error":
                # 错误处理
                error_code = payload.get("code", "UNKNOWN")
                error_msg = payload.get("message", "未知错误")
                await assistant_msg.stream_token(f"\n\n❌ {error_msg}")
                full_content += f"\n\n❌ {error_msg}"  # 累积错误内容
                break

        # 完成流式输出
        # 完成流式输出 - 最后一次update()确保消息完成状态
        await assistant_msg.update()
        print(f"[DEBUG] UI流式输出完成，总token数: {token_count}")

        # 添加完成标记到侧栏
        completion_log = "✅ 处理完成"
        await cl.Message(content=completion_log, author="系统日志").send()

        # 记录助手回复到对话历史
        session = get_session(session_id)
        if full_content:
            session.add_message("assistant", full_content)

    except Exception as e:
        # 确保token_count在异常情况下也有默认值
        token_count = 0
        error_msg = await cl.Message(content=f"❌ 处理失败: {str(e)}", author="助手").send()

        # 记录错误消息到对话历史
        try:
            session = get_session(session_id)
            session.add_message("assistant", f"❌ 处理失败: {str(e)}")
        except:
            pass


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
