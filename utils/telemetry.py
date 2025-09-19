"""
Telemetry v1 模块
记录 6 类关键事件到 logs/errors.jsonl
"""
import json
import time
import uuid
from typing import Dict, Any, Optional, List
from pathlib import Path
from enum import Enum

from logger import get_logger

logger = get_logger()


class TelemetryEvent(Enum):
    """遥测事件类型"""
    ASK_USER_IGNORED = "ASK_USER_IGNORED"      # 用户忽略活跃任务，开始新任务
    ASK_USER_OPEN = "ASK_USER_OPEN"            # AskUser问题打开
    ASK_USER_RESUME = "ASK_USER_RESUME"        # 用户回答AskUser问题
    SESSION_MISMATCH = "SESSION_MISMATCH"       # Session不匹配
    PLANNER_NON_JSON = "PLANNER_NON_JSON"     # Planner JSON 解析失败
    EXEC_TOOL_FAIL = "EXEC_TOOL_FAIL"          # 工具执行失败
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"        # 预算超限
    SPEC_MISMATCH = "SPEC_MISMATCH"            # 产物不满足 success_criteria
    WRITE_OUT_OF_SANDBOX = "WRITE_OUT_OF_SANDBOX"  # 越界写盘


class TelemetryStage(Enum):
    """遥测阶段"""
    ASK_USER = "ask_user"
    PLAN = "plan"
    ACT = "act"
    JUDGE = "judge"


class TelemetryLogger:
    """遥测日志记录器"""

    def __init__(self, log_file: str = "./logs/errors.jsonl"):
        """
        初始化遥测记录器

        Args:
            log_file: 日志文件路径
        """
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def log_event(self,
                  stage: TelemetryStage,
                  event: TelemetryEvent,
                  user_query: str = "",
                  context: Dict[str, Any] = None,
                  plan_excerpt: Dict[str, Any] = None,
                  limits: Dict[str, Any] = None,
                  model: Dict[str, str] = None) -> str:
        """
        记录遥测事件

        Args:
            stage: 事件发生的阶段
            event: 事件类型
            user_query: 用户查询（可选）
            context: 事件上下文信息
            plan_excerpt: 计划摘要（可选）
            limits: 限制信息（可选）
            model: 模型信息（可选）

        Returns:
            request_id: 生成的请求ID
        """
        request_id = str(uuid.uuid4())

        # 构建日志条目
        log_entry = {
            "ts": time.time(),
            "request_id": request_id,
            "stage": stage.value,
            "event": event.value,
            "user_query": user_query[:500] if user_query else "",  # 限制长度
            "context": context or {},
            "plan_excerpt": plan_excerpt or {},
            "limits": limits or {},
            "model": model or {}
        }

        # 写入日志文件
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                json.dump(log_entry, f, ensure_ascii=False)
                f.write('\n')

            logger.info(f"遥测事件已记录: {event.value} ({stage.value})")

        except Exception as e:
            logger.error(f"遥测日志写入失败: {e}")

        return request_id

    def log_ask_user_ignored(self,
                            user_query: str,
                            reason: str = "new_task_requested_with_active_task",
                            had_active_task: bool = True,
                            task_age_seconds: float = 0) -> str:
        """记录 ASK_USER_IGNORED 事件"""
        return self.log_event(
            stage=TelemetryStage.ASK_USER,
            event=TelemetryEvent.ASK_USER_IGNORED,
            user_query=user_query,
            context={
                "reason": reason,
                "had_active_task": had_active_task,
                "task_age_seconds": task_age_seconds
            }
        )

    def log_planner_non_json(self,
                           user_query: str,
                           error: str,
                           attempt: int = 1,
                           raw_response: str = "") -> str:
        """记录 PLANNER_NON_JSON 事件"""
        return self.log_event(
            stage=TelemetryStage.PLAN,
            event=TelemetryEvent.PLANNER_NON_JSON,
            user_query=user_query,
            context={
                "error": error,
                "attempt": attempt,
                "raw_response": raw_response[:500]  # 限制长度
            }
        )

    def log_exec_tool_fail(self,
                          tool_name: str,
                          step_id: str,
                          error: Dict[str, Any],
                          inputs: Dict[str, Any]) -> str:
        """记录 EXEC_TOOL_FAIL 事件"""
        return self.log_event(
            stage=TelemetryStage.ACT,
            event=TelemetryEvent.EXEC_TOOL_FAIL,
            context={
                "tool": tool_name,
                "step_id": step_id,
                "error": error,
                "inputs": inputs
            }
        )

    def log_budget_exceeded(self,
                           user_query: str,
                           reason: str = "total_tool_calls_exceeded",
                           current: int = 0,
                           limit: int = 0) -> str:
        """记录 BUDGET_EXCEEDED 事件"""
        return self.log_event(
            stage=TelemetryStage.ACT,
            event=TelemetryEvent.BUDGET_EXCEEDED,
            user_query=user_query,
            context={"reason": reason, "current": current, "limit": limit},
            limits={"tool_calls_used": current, "budget": {"max_calls": limit}}
        )

    def log_spec_mismatch(self,
                         iteration: int,
                         missing: List[str],
                         questions: List[str]) -> str:
        """记录 SPEC_MISMATCH 事件"""
        return self.log_event(
            stage=TelemetryStage.JUDGE,
            event=TelemetryEvent.SPEC_MISMATCH,
            context={
                "iteration": iteration,
                "missing": missing,
                "questions": questions
            }
        )

    def log_write_out_of_sandbox(self,
                               path: str,
                               error: str,
                               operation: str = "write") -> str:
        """记录 WRITE_OUT_OF_SANDBOX 事件"""
        return self.log_event(
            stage=TelemetryStage.ACT,
            event=TelemetryEvent.WRITE_OUT_OF_SANDBOX,
            context={
                "path": path,
                "error": error,
                "operation": operation
            }
        )


# 全局遥测记录器实例
_telemetry_logger = None


def get_telemetry_logger() -> TelemetryLogger:
    """获取遥测记录器实例"""
    global _telemetry_logger
    if _telemetry_logger is None:
        _telemetry_logger = TelemetryLogger()
    return _telemetry_logger


def log_event(stage: TelemetryStage,
              event: TelemetryEvent,
              user_query: str = "",
              context: Dict[str, Any] = None,
              plan_excerpt: Dict[str, Any] = None,
              limits: Dict[str, Any] = None,
              model: Dict[str, str] = None) -> str:
    """
    便捷函数：记录遥测事件

    Args:
        stage: 事件发生的阶段
        event: 事件类型
        user_query: 用户查询
        context: 事件上下文
        plan_excerpt: 计划摘要
        limits: 限制信息
        model: 模型信息

    Returns:
        request_id: 请求ID
    """
    logger = get_telemetry_logger()
    return logger.log_event(stage, event, user_query, context, plan_excerpt, limits, model)


# 便捷函数 - 直接记录特定事件
def log_ask_user_ignored(user_query: str, **kwargs) -> str:
    """记录 ASK_USER_IGNORED 事件"""
    logger = get_telemetry_logger()
    return logger.log_ask_user_ignored(user_query, **kwargs)


def log_planner_non_json(user_query: str, **kwargs) -> str:
    """记录 PLANNER_NON_JSON 事件"""
    logger = get_telemetry_logger()
    return logger.log_planner_non_json(user_query, **kwargs)


def log_exec_tool_fail(**kwargs) -> str:
    """记录 EXEC_TOOL_FAIL 事件"""
    logger = get_telemetry_logger()
    return logger.log_exec_tool_fail(**kwargs)


def log_budget_exceeded(user_query: str, **kwargs) -> str:
    """记录 BUDGET_EXCEEDED 事件"""
    logger = get_telemetry_logger()
    return logger.log_budget_exceeded(user_query, **kwargs)


def log_spec_mismatch(**kwargs) -> str:
    """记录 SPEC_MISMATCH 事件"""
    logger = get_telemetry_logger()
    return logger.log_spec_mismatch(**kwargs)


def log_write_out_of_sandbox(**kwargs) -> str:
    """记录 WRITE_OUT_OF_SANDBOX 事件"""
    logger = get_telemetry_logger()
    return logger.log_write_out_of_sandbox(**kwargs)


def log_ask_user_open(session_id: str, ask_id: str, question: str, step_id: str = "", active_task_id: str = "") -> str:
    """记录 ASK_USER_OPEN 事件"""
    logger = get_telemetry_logger()
    return logger.log_event(
        stage=TelemetryStage.ASK_USER,
        event=TelemetryEvent.ASK_USER_OPEN,
        context={
            "session_id": session_id,
            "active_task_id": active_task_id,
            "ask_id": ask_id,
            "step_id": step_id,
            "question": question
        }
    )


def log_ask_user_resume(session_id: str, ask_id: str, answer: str, latency_ms: int = 0, step_id: str = "", active_task_id: str = "") -> str:
    """记录 ASK_USER_RESUME 事件"""
    logger = get_telemetry_logger()
    return logger.log_event(
        stage=TelemetryStage.ASK_USER,
        event=TelemetryEvent.ASK_USER_RESUME,
        context={
            "session_id": session_id,
            "active_task_id": active_task_id,
            "ask_id": ask_id,
            "step_id": step_id,
            "answer_len": len(answer),
            "latency_ms": latency_ms
        }
    )


def log_session_mismatch(session_id: str, expected_session_id: str, actual_session_id: str,
                        expected_ask_id: str = "", actual_ask_id: str = "") -> str:
    """记录 SESSION_MISMATCH 事件"""
    logger = get_telemetry_logger()
    return logger.log_event(
        stage=TelemetryStage.ASK_USER,
        event=TelemetryEvent.SESSION_MISMATCH,
        context={
            "expected_session_id": expected_session_id,
            "actual_session_id": actual_session_id,
            "expected_ask_id": expected_ask_id,
            "actual_ask_id": actual_ask_id
        }
    )
