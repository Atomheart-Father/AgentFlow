"""
Session管理器 - 处理session_id绑定和粘性会话
"""
import uuid
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class SessionManager:
    """Session管理器"""

    @staticmethod
    def generate_session_id() -> str:
        """生成唯一的session_id"""
        return str(uuid.uuid4())

    @staticmethod
    def get_or_create_session_id(cl_user_session) -> str:
        """获取或创建session_id"""
        session_id = cl_user_session.get("session_id")
        if not session_id:
            session_id = SessionManager.generate_session_id()
            cl_user_session.set("session_id", session_id)
            logger.info(f"创建新session_id: {session_id}")
        else:
            logger.debug(f"使用现有session_id: {session_id}")
        return session_id

    @staticmethod
    def validate_session_context(session_id: str, context: Optional[Dict[str, Any]] = None) -> bool:
        """验证session上下文"""
        if not context:
            logger.warning(f"Session {session_id}: 上下文为空")
            return False

        context_session_id = context.get("session_id")
        if context_session_id != session_id:
            logger.error(f"Session ID不匹配: 期望 {session_id}, 收到 {context_session_id}")
            return False

        return True

    @staticmethod
    def validate_ask_id_consistency(session, current_ask_id: str) -> bool:
        """验证ask_id一致性"""
        if not session.has_pending_ask():
            logger.warning("Session没有pending_ask，但收到用户回答")
            return False

        pending_ask = session.pending_ask
        if not hasattr(pending_ask, 'ask_id'):
            logger.warning("PendingAsk没有ask_id字段")
            return False

        if pending_ask.ask_id != current_ask_id:
            logger.error(f"AskID不匹配: 期望 {pending_ask.ask_id}, 收到 {current_ask_id}")
            return False

        return True

    @staticmethod
    def cleanup_session_state(cl_user_session):
        """清理session状态"""
        cl_user_session.set("waiting_for_user_input", False)
        cl_user_session.set("current_ask_id", "")
        logger.debug("清理session状态完成")

    @staticmethod
    def log_session_event(session_id: str, event_type: str, details: Optional[Dict[str, Any]] = None):
        """记录session事件"""
        details_str = f" - {details}" if details else ""
        logger.info(f"Session {session_id}: {event_type}{details_str}")


# 全局实例
session_manager = SessionManager()
