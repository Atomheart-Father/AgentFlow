"""
Session管理器 - 处理session_id绑定和粘性会话
"""
import uuid
import json
import os
from pathlib import Path
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
    def save_execution_state(session_id: str, execution_state):
        """保存execution_state到磁盘"""
        try:
            # 创建session目录
            session_dir = Path("data/sessions")
            session_dir.mkdir(parents=True, exist_ok=True)

            # 保存execution_state
            state_file = session_dir / f"{session_id}_execution.json"

            # 使用Pydantic的model_dump进行序列化
            if hasattr(execution_state, 'model_dump'):
                state_data = execution_state.model_dump()
            else:
                # 回退到手动序列化
                state_data = {
                    "cursor_index": execution_state.cursor_index,
                    "done_set": list(execution_state.done_set),
                    "asked_map": dict(execution_state.asked_map),
                    "answers": dict(execution_state.answers),
                    "artifacts": dict(execution_state.artifacts),
                    "errors": list(execution_state.errors),
                    "completed_steps": list(execution_state.completed_steps),
                    "asked_questions": list(execution_state.asked_questions)
                }

            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, ensure_ascii=False, indent=2)

            logger.debug(f"已保存execution_state到 {state_file}")

        except Exception as e:
            logger.error(f"保存execution_state失败: {e}")

    @staticmethod
    def load_execution_state(session_id: str):
        """从磁盘加载execution_state"""
        try:
            state_file = Path("data/sessions") / f"{session_id}_execution.json"
            if not state_file.exists():
                return None

            with open(state_file, 'r', encoding='utf-8') as f:
                state_data = json.load(f)

            # 这里应该返回反序列化的ExecutionState对象
            # 但由于导入循环问题，我们先返回字典，让调用方处理
            logger.debug(f"已加载execution_state从 {state_file}")
            return state_data

        except Exception as e:
            logger.error(f"加载execution_state失败: {e}")
            return None

    @staticmethod
    def log_session_event(session_id: str, event_type: str, details: Optional[Dict[str, Any]] = None):
        """记录session事件"""
        details_str = f" - {details}" if details else ""
        logger.info(f"Session {session_id}: {event_type}{details_str}")


# 全局实例
session_manager = SessionManager()
