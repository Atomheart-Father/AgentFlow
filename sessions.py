"""
会话状态管理模块
提供 sessions[session_id] = { active_task, pending_ask, state } 支持
支持 AskUser → 续跑闭环，会话态自动管理
"""
import time
import uuid
from typing import Dict, Any, Optional
from orchestrator.orchestrator import SessionState, ActiveTask, PendingAsk
from orchestrator import get_session
from logger import get_logger

logger = get_logger()


def get_session_state(session_id: str) -> SessionState:
    """
    获取会话状态 - 兼容原有 orchestrator.get_session

    Args:
        session_id: 会话ID

    Returns:
        SessionState: 会话状态对象
    """
    return get_session(session_id)


def set_pending_ask(session_id: str, question: str, expects: str = "answer") -> bool:
    """
    设置挂起的问题状态

    Args:
        session_id: 会话ID
        question: 问题内容
        expects: 期望的答案类型

    Returns:
        bool: 设置是否成功
    """
    try:
        session = get_session(session_id)
        session.set_pending_ask(question, expects)
        logger.info(f"设置pending_ask成功: {session_id} -> {question}")
        return True
    except Exception as e:
        logger.error(f"设置pending_ask失败: {e}")
        return False


def resume_with_answer(session_id: str, answer: str, ask_id: str = None, output_key: str = None) -> Optional[SessionState]:
    """
    使用用户答案恢复任务执行 - 支持宽松字段兼容

    Args:
        session_id: 会话ID
        answer: 用户答案（兼容value等别名）
        ask_id: 询问ID（可选，用于验证）
        output_key: 输出键名（可选，优先使用）

    Returns:
        SessionState: 更新后的会话状态，如果失败返回None
    """
    try:
        session = get_session(session_id)

        if not session.has_pending_ask():
            logger.warning(f"会话 {session_id} 没有挂起的问题")
            return None

        # 验证ask_id一致性（如果提供）
        if ask_id and session.pending_ask.ask_id != ask_id:
            logger.error(f"AskID不匹配: 期望 {session.pending_ask.ask_id}, 收到 {ask_id}")
            return None

        # 清除pending状态
        pending_ask = session.pending_ask
        session.clear_pending_ask()

        # 将答案填入execution state
        if session.active_task and session.active_task.execution_state:
            # 确定输出键名
            if output_key:
                # 优先使用传入的output_key
                final_output_key = output_key
            else:
                # 根据expects类型推断output_key
                expects = pending_ask.expects.lower()
                if "city" in expects:
                    final_output_key = "user_city"
                elif "date" in expects:
                    final_output_key = "user_date"
                else:
                    final_output_key = "user_answer"

            # 写入答案到execution state
            session.active_task.execution_state.set_artifact(final_output_key, answer)

            # 清除ask_user_pending状态
            session.active_task.execution_state.remove_artifact("ask_user_pending")

            logger.info(f"用户答案已写入execution_state: {final_output_key} = {answer}")
            return session
        else:
            logger.warning(f"会话 {session_id} 没有活跃任务")
            return None

    except Exception as e:
        logger.error(f"恢复任务失败: {e}")
        return None


def is_new_task_request(user_input: str) -> bool:
    """
    检查是否是新任务请求

    Args:
        user_input: 用户输入

    Returns:
        bool: 是否是新任务请求
    """
    new_task_keywords = [
        "新的问题", "new question", "reset", "重来", "重新开始",
        "新任务", "new task", "clear", "清除", "开始新任务"
    ]
    query_lower = user_input.lower().strip()
    return any(keyword in query_lower for keyword in new_task_keywords)


def cleanup_session(session_id: str) -> bool:
    """
    清理会话状态 - 用于新任务开始

    Args:
        session_id: 会话ID

    Returns:
        bool: 清理是否成功
    """
    try:
        session = get_session(session_id)
        session.end_task()
        logger.info(f"会话清理完成: {session_id}")
        return True
    except Exception as e:
        logger.error(f"会话清理失败: {e}")
        return False


def get_session_summary(session_id: str) -> Dict[str, Any]:
    """
    获取会话摘要信息

    Args:
        session_id: 会话ID

    Returns:
        Dict: 会话摘要信息
    """
    try:
        session = get_session(session_id)

        summary = {
            "session_id": session_id,
            "has_active_task": session.active_task is not None,
            "has_pending_ask": session.has_pending_ask(),
            "created_at": session.created_at,
            "task_age_seconds": None,
            "pending_question": None
        }

        if session.active_task:
            summary["task_age_seconds"] = time.time() - session.active_task.created_at

        if session.has_pending_ask():
            summary["pending_question"] = session.pending_ask.question

        return summary

    except Exception as e:
        logger.error(f"获取会话摘要失败: {e}")
        return {"error": str(e)}


def list_active_sessions() -> Dict[str, Dict[str, Any]]:
    """
    列出所有活跃会话

    Returns:
        Dict: 会话ID到摘要的映射
    """
    from orchestrator.orchestrator import _sessions

    active_sessions = {}
    current_time = time.time()

    for session_id, session in _sessions.items():
        # 检查是否有活跃任务或挂起问题
        if session.active_task or session.has_pending_ask():
            # 检查任务是否仍然活跃（1小时超时）
            if session.active_task and current_time - session.active_task.created_at > 3600:
                continue

            active_sessions[session_id] = get_session_summary(session_id)

    return active_sessions


def cleanup_expired_sessions():
    """清理过期的会话（后台任务）"""
    from orchestrator.orchestrator import cleanup_old_sessions
    cleanup_old_sessions()


# 便捷函数 - 提供给UI层使用
def get_or_create_session(session_id: Optional[str] = None) -> str:
    """
    获取或创建会话ID

    Args:
        session_id: 现有会话ID，如果为None则创建新的

    Returns:
        str: 会话ID
    """
    if session_id is None:
        session_id = str(uuid.uuid4())

    # 获取会话（会自动创建如果不存在）
    get_session(session_id)
    return session_id
