"""
前后端事件协议定义 - 统一8种事件类型
"""
from typing import Dict, Any, Optional
from pydantic import BaseModel


class BaseEvent(BaseModel):
    """基础事件模型"""
    type: str
    payload: Dict[str, Any]


class AssistantContentEvent(BaseEvent):
    """助手内容增量事件 - 只能进聊天气泡"""
    type: str = "assistant_content"
    payload: Dict[str, Any] = {"delta": ""}  # 只包含增量内容


class StatusEvent(BaseEvent):
    """状态/进度事件 - 走侧栏/状态栏"""
    type: str = "status"
    payload: Dict[str, Any] = {"message": ""}


class ToolTraceEvent(BaseEvent):
    """工具调用与返回事件 - 走侧栏/工具面板"""
    type: str = "tool_trace"
    payload: Dict[str, Any] = {"tool": "", "action": "", "result": ""}


class DebugEvent(BaseEvent):
    """调试细节事件 - 走侧栏/调试面板"""
    type: str = "debug"
    payload: Dict[str, Any] = {"level": "info", "message": ""}


class AskUserOpenEvent(BaseEvent):
    """打开用户提问事件 - 显示提问卡片"""
    type: str = "ask_user_open"
    payload: Dict[str, Any] = {"ask_id": "", "question": "", "hints": ""}


class AskUserCloseEvent(BaseEvent):
    """关闭用户提问事件 - 用户已回答"""
    type: str = "ask_user_close"
    payload: Dict[str, Any] = {"ask_id": "", "accepted": True}


class FinalAnswerEvent(BaseEvent):
    """最终答案事件 - 结束标记"""
    type: str = "final_answer"
    payload: Dict[str, Any] = {"answer": "", "summary": ""}


class ErrorEvent(BaseEvent):
    """错误事件"""
    type: str = "error"
    payload: Dict[str, Any] = {"code": "", "message": ""}


# 事件类型映射
EVENT_TYPES = {
    "assistant_content": AssistantContentEvent,
    "status": StatusEvent,
    "tool_trace": ToolTraceEvent,
    "debug": DebugEvent,
    "ask_user_open": AskUserOpenEvent,
    "ask_user_close": AskUserCloseEvent,
    "final_answer": FinalAnswerEvent,
    "error": ErrorEvent,
}


def create_event(event_type: str, **payload) -> Dict[str, Any]:
    """创建标准事件"""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"未知事件类型: {event_type}")

    event_class = EVENT_TYPES[event_type]
    event = event_class(payload=payload)
    return event.dict()


def validate_event(event: Dict[str, Any]) -> bool:
    """验证事件格式"""
    if not isinstance(event, dict) or "type" not in event or "payload" not in event:
        return False

    event_type = event["type"]
    if event_type not in EVENT_TYPES:
        return False

    # 可以使用pydantic验证更详细的内容
    return True
