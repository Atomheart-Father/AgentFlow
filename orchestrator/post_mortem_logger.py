"""
Post-Mortem Logger模块 - 用于备现身复盘的详细日志记录
记录完整的执行轨迹、性能指标和错误信息，便于后续分析和改进
"""
import json
import time
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
import threading

from logger import get_logger

logger = get_logger()


class PostMortemLogger:
    """备现身复盘日志记录器"""

    def __init__(self, log_dir: str = "logs/post_mortem"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.current_session: Optional[Dict[str, Any]] = None
        self.session_lock = threading.Lock()

    def start_session(self, session_id: str, user_query: str, mode: str = "m3") -> str:
        """开始新的会话记录"""
        with self.session_lock:
            self.current_session = {
                "session_id": session_id,
                "user_query": user_query,
                "mode": mode,  # m3, traditional
                "start_time": datetime.now().isoformat(),
                "end_time": None,
                "total_duration": 0.0,
                "phases": [],  # PLAN, ACT, JUDGE等阶段的详细记录
                "tool_calls": [],  # 工具调用记录
                "errors": [],  # 错误记录
                "performance_metrics": {},  # 性能指标
                "llm_calls": [],  # LLM调用记录
                "user_interactions": [],  # 用户交互记录
                "final_result": None
            }

            logger.info(f"开始备现身复盘会话: {session_id}")
            return session_id

    def end_session(self, final_result: Dict[str, Any], error_message: Optional[str] = None):
        """结束会话记录"""
        with self.session_lock:
            if not self.current_session:
                logger.warning("没有活跃的会话记录")
                return

            self.current_session["end_time"] = datetime.now().isoformat()

            if self.current_session["start_time"]:
                start_time = datetime.fromisoformat(self.current_session["start_time"])
                end_time = datetime.fromisoformat(self.current_session["end_time"])
                self.current_session["total_duration"] = (end_time - start_time).total_seconds()

            self.current_session["final_result"] = final_result
            if error_message:
                self.current_session["errors"].append({
                    "type": "session_error",
                    "message": error_message,
                    "timestamp": datetime.now().isoformat()
                })

            # 保存到文件
            self._save_session()
            logger.info(f"结束备现身复盘会话: {self.current_session['session_id']}")

    def log_phase_start(self, phase: str, iteration: int):
        """记录阶段开始"""
        if not self.current_session:
            return

        phase_record = {
            "phase": phase,
            "iteration": iteration,
            "start_time": datetime.now().isoformat(),
            "end_time": None,
            "duration": 0.0,
            "status": "in_progress",
            "details": {},
            "metrics": {}
        }

        with self.session_lock:
            self.current_session["phases"].append(phase_record)

        logger.info(f"阶段开始: {phase} (第{iteration}轮)")

    def log_phase_end(self, phase: str, status: str, details: Dict[str, Any] = None):
        """记录阶段结束"""
        if not self.current_session:
            return

        with self.session_lock:
            for phase_record in reversed(self.current_session["phases"]):
                if phase_record["phase"] == phase and phase_record["status"] == "in_progress":
                    phase_record["end_time"] = datetime.now().isoformat()
                    phase_record["status"] = status
                    if details:
                        phase_record["details"] = details

                    if phase_record["start_time"]:
                        start_time = datetime.fromisoformat(phase_record["start_time"])
                        end_time = datetime.fromisoformat(phase_record["end_time"])
                        phase_record["duration"] = (end_time - start_time).total_seconds()

                    logger.info(f"阶段结束: {phase}, 状态: {status}, 耗时: {phase_record['duration']:.2f}s")
                    break

    def log_tool_call(self, tool_name: str, parameters: Dict[str, Any],
                     result: Any, duration: float, success: bool):
        """记录工具调用"""
        if not self.current_session:
            return

        tool_call_record = {
            "tool_name": tool_name,
            "parameters": parameters,
            "result": str(result)[:1000],  # 限制结果长度
            "duration": duration,
            "success": success,
            "timestamp": datetime.now().isoformat()
        }

        with self.session_lock:
            self.current_session["tool_calls"].append(tool_call_record)

        logger.info(f"工具调用: {tool_name}, 成功: {success}, 耗时: {duration:.2f}s")

    def log_llm_call(self, model: str, messages: List[Dict[str, str]],
                     response: str, tokens_used: int, duration: float):
        """记录LLM调用"""
        if not self.current_session:
            return

        llm_call_record = {
            "model": model,
            "messages_count": len(messages),
            "response_length": len(response),
            "tokens_used": tokens_used,
            "duration": duration,
            "timestamp": datetime.now().isoformat(),
            "input_preview": messages[0]["content"][:200] if messages else "",
            "output_preview": response[:200]
        }

        with self.session_lock:
            self.current_session["llm_calls"].append(llm_call_record)

        logger.info(f"LLM调用: {model}, Token: {tokens_used}, 耗时: {duration:.2f}s")

    def log_error(self, error_type: str, message: str, context: Dict[str, Any] = None):
        """记录错误"""
        if not self.current_session:
            return

        error_record = {
            "type": error_type,
            "message": message,
            "context": context or {},
            "timestamp": datetime.now().isoformat()
        }

        with self.session_lock:
            self.current_session["errors"].append(error_record)

        logger.error(f"错误记录: {error_type} - {message}")

    def log_user_interaction(self, interaction_type: str, question: str,
                           answer: str = None, duration: float = None):
        """记录用户交互"""
        if not self.current_session:
            return

        interaction_record = {
            "type": interaction_type,  # ask_user, answer_provided, etc.
            "question": question,
            "answer": answer,
            "duration": duration,
            "timestamp": datetime.now().isoformat()
        }

        with self.session_lock:
            self.current_session["user_interactions"].append(interaction_record)

        logger.info(f"用户交互: {interaction_type} - {question}")

    def log_performance_metric(self, metric_name: str, value: Any):
        """记录性能指标"""
        if not self.current_session:
            return

        with self.session_lock:
            self.current_session["performance_metrics"][metric_name] = value

        logger.info(f"性能指标: {metric_name} = {value}")

    def _save_session(self):
        """保存会话记录到文件"""
        if not self.current_session:
            return

        session_id = self.current_session["session_id"]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{session_id}.json"

        filepath = self.log_dir / filename

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.current_session, f, ensure_ascii=False, indent=2)

            logger.info(f"备现身复盘日志已保存: {filepath}")

            # 同时保存一个简化的摘要文件
            summary = self._create_summary()
            summary_filepath = self.log_dir / f"{timestamp}_{session_id}_summary.json"
            with open(summary_filepath, 'w', encoding='utf-8') as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"保存备现身复盘日志失败: {e}")

    def _create_summary(self) -> Dict[str, Any]:
        """创建会话摘要"""
        if not self.current_session:
            return {}

        session = self.current_session

        # 计算各项统计
        total_tool_calls = len(session["tool_calls"])
        successful_tool_calls = sum(1 for call in session["tool_calls"] if call["success"])
        total_llm_calls = len(session["llm_calls"])
        total_errors = len(session["errors"])

        # 计算阶段耗时
        phase_durations = {}
        for phase in session["phases"]:
            phase_durations[phase["phase"]] = phase.get("duration", 0)

        summary = {
            "session_id": session["session_id"],
            "user_query": session["user_query"][:100] + "..." if len(session["user_query"]) > 100 else session["user_query"],
            "mode": session["mode"],
            "start_time": session["start_time"],
            "total_duration": session["total_duration"],
            "status": session["final_result"].get("status", "unknown") if session["final_result"] else "unknown",
            "statistics": {
                "tool_calls": {
                    "total": total_tool_calls,
                    "successful": successful_tool_calls,
                    "success_rate": successful_tool_calls / total_tool_calls if total_tool_calls > 0 else 0
                },
                "llm_calls": {
                    "total": total_llm_calls,
                    "total_tokens": sum(call["tokens_used"] for call in session["llm_calls"])
                },
                "errors": {
                    "total": total_errors,
                    "types": list(set(error["type"] for error in session["errors"]))
                },
                "phases": phase_durations
            },
            "user_interactions": len(session["user_interactions"]),
            "performance_metrics": session["performance_metrics"]
        }

        return summary


# 全局实例
_post_mortem_logger = None

def get_post_mortem_logger() -> PostMortemLogger:
    """获取全局备现身复盘日志记录器"""
    global _post_mortem_logger
    if _post_mortem_logger is None:
        _post_mortem_logger = PostMortemLogger()
    return _post_mortem_logger
