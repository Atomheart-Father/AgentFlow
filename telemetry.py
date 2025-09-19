"""
Telemetry监控系统 - 错误追踪和性能监控
"""
import json
import time
from typing import Dict, Any, Optional
from enum import Enum
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class TelemetryEvent(Enum):
    """Telemetry事件类型"""
    PLAN_NON_JSON = "plan_non_json"
    EXEC_TOOL_FAIL = "exec_tool_fail"
    ASK_USER_OPEN = "ask_user_open"
    ASK_USER_RESUME = "ask_user_resume"
    SESSION_MISMATCH = "session_mismatch"
    WS_BACKPRESSURE = "ws_backpressure"
    STREAM_TOKEN_COUNT = "stream_token_count"
    PROCESS_START = "process_start"
    PROCESS_END = "process_end"
    ERROR_OCCURRED = "error_occurred"


class TelemetryManager:
    """Telemetry管理器"""

    def __init__(self, log_file: str = "logs/errors.jsonl"):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # 性能监控数据
        self.stream_stats = {
            "session_id": None,
            "start_time": None,
            "token_count": 0,
            "last_token_time": None,
            "backpressure_count": 0
        }

    def log_event(self, event_type: TelemetryEvent, session_id: str = "",
                  active_task_id: str = "", payload: Optional[Dict[str, Any]] = None) -> None:
        """记录telemetry事件"""
        try:
            event_data = {
                "ts": time.time(),
                "session_id": session_id or "unknown",
                "active_task_id": active_task_id or "unknown",
                "type": event_type.value,
                "payload": payload or {}
            }

            # 写入JSONL文件
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(event_data, ensure_ascii=False) + '\n')

            # 同时记录到logger
            logger.info(f"Telemetry: {event_type.value} - Session: {session_id}")

        except Exception as e:
            logger.error(f"Telemetry记录失败: {e}")

    def start_stream_monitoring(self, session_id: str) -> None:
        """开始流式输出监控"""
        self.stream_stats = {
            "session_id": session_id,
            "start_time": time.time(),
            "token_count": 0,
            "last_token_time": time.time(),
            "backpressure_count": 0
        }
        self.log_event(TelemetryEvent.PROCESS_START, session_id)

    def record_stream_token(self, token_count: int = 1) -> None:
        """记录流式token"""
        if not self.stream_stats["session_id"]:
            return

        current_time = time.time()
        self.stream_stats["token_count"] += token_count
        self.stream_stats["last_token_time"] = current_time

        # 检查是否出现backpressure（2秒内没有新token）
        if self.stream_stats["start_time"] and (current_time - self.stream_stats["last_token_time"]) > 2:
            self.stream_stats["backpressure_count"] += 1
            self.log_event(
                TelemetryEvent.WS_BACKPRESSURE,
                self.stream_stats["session_id"],
                payload={
                    "token_count": self.stream_stats["token_count"],
                    "backpressure_count": self.stream_stats["backpressure_count"],
                    "time_since_last_token": current_time - self.stream_stats["last_token_time"]
                }
            )

    def end_stream_monitoring(self, success: bool = True) -> None:
        """结束流式输出监控"""
        if not self.stream_stats["session_id"]:
            return

        end_time = time.time()
        duration = end_time - (self.stream_stats["start_time"] or end_time)

        self.log_event(
            TelemetryEvent.PROCESS_END,
            self.stream_stats["session_id"],
            payload={
                "success": success,
                "duration": duration,
                "total_tokens": self.stream_stats["token_count"],
                "backpressure_count": self.stream_stats["backpressure_count"]
            }
        )

        # 重置统计数据
        self.stream_stats = {
            "session_id": None,
            "start_time": None,
            "token_count": 0,
            "last_token_time": None,
            "backpressure_count": 0
        }

    def log_error(self, error_type: str, session_id: str, error: Exception,
                  context: Optional[Dict[str, Any]] = None) -> None:
        """记录错误"""
        payload = {
            "error_type": error_type,
            "error_message": str(error),
            "error_class": error.__class__.__name__
        }

        if context:
            payload.update(context)

        self.log_event(TelemetryEvent.ERROR_OCCURRED, session_id, payload=payload)

    # 便捷方法
    def log_plan_error(self, session_id: str, plan_text: str, error: Exception) -> None:
        """记录规划错误"""
        self.log_event(
            TelemetryEvent.PLAN_NON_JSON,
            session_id,
            payload={
                "plan_text": plan_text[:500],  # 只记录前500字符
                "error": str(error)
            }
        )

    def log_tool_error(self, session_id: str, tool_name: str, error: Exception) -> None:
        """记录工具执行错误"""
        self.log_event(
            TelemetryEvent.EXEC_TOOL_FAIL,
            session_id,
            payload={
                "tool_name": tool_name,
                "error": str(error)
            }
        )

    def log_ask_user_event(self, session_id: str, ask_id: str, question: str, event_type: str = "open") -> None:
        """记录AskUser事件"""
        event = TelemetryEvent.ASK_USER_OPEN if event_type == "open" else TelemetryEvent.ASK_USER_RESUME
        self.log_event(
            event,
            session_id,
            payload={
                "ask_id": ask_id,
                "question": question
            }
        )

    def log_session_mismatch(self, session_id: str, expected: str, actual: str) -> None:
        """记录session不匹配"""
        self.log_event(
            TelemetryEvent.SESSION_MISMATCH,
            session_id,
            payload={
                "expected": expected,
                "actual": actual
            }
        )


# 全局telemetry实例
telemetry = TelemetryManager()
