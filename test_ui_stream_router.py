import pytest

from ui_gradio import ChatUI


def test_route_stream_event_assistant_content():
    ui = ChatUI()
    chunk = {"type": "assistant_content", "content": "Hello"}
    routed = ui._route_stream_event(chunk)
    assert routed["chat_append"] == "Hello"
    assert routed["status_text"] is None
    assert routed["error_text"] is None


def test_route_stream_event_status():
    ui = ChatUI()
    chunk = {"type": "status", "message": "规划中"}
    routed = ui._route_stream_event(chunk)
    assert routed["chat_append"] is None
    assert "规划中" in routed["status_text"]


def test_route_stream_event_error():
    ui = ChatUI()
    chunk = {"type": "error", "message": "失败"}
    routed = ui._route_stream_event(chunk)
    assert routed["chat_append"] is None
    assert routed["status_text"] is None
    assert routed["error_text"] == "失败"


def test_route_stream_event_compat_content():
    ui = ChatUI()
    chunk = {"type": "content", "content": "Legacy"}
    routed = ui._route_stream_event(chunk)
    assert routed["chat_append"] == "Legacy"

