"""
Telemetry v1 核心实现
错误与偏差数据集收集和分析系统
"""

import json
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from pathlib import Path
from enum import Enum
from pydantic import BaseModel, Field
import threading

from logger import get_logger

logger = get_logger()


class TelemetryEvent(str, Enum):
    """Telemetry事件类型枚举"""
    PLANNER_NON_JSON = "PLANNER_NON_JSON"
    PLAN_EMPTY_OR_USELESS = "PLAN_EMPTY_OR_USELESS"
    EXEC_TOOL_FAIL = "EXEC_TOOL_FAIL"
    EXEC_PARAM_INVALID = "EXEC_PARAM_INVALID"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    ASK_USER_IGNORED = "ASK_USER_IGNORED"
    JUDGE_LOOP = "JUDGE_LOOP"
    SPEC_MISMATCH = "SPEC_MISMATCH"


class TelemetryStage(str, Enum):
    """执行阶段枚举"""
    PLAN = "PLAN"
    ACT = "ACT"
    JUDGE = "JUDGE"
    ASK_USER = "ASK_USER"


class TelemetryRecord(BaseModel):
    """Telemetry记录结构"""
    ts: str = Field(..., description="ISO格式时间戳")
    request_id: str = Field(..., description="请求唯一ID")
    stage: TelemetryStage = Field(..., description="执行阶段")
    event: TelemetryEvent = Field(..., description="事件类型")
    user_query: str = Field(..., description="用户查询")
    context: Dict[str, Any] = Field(default_factory=dict, description="事件上下文")
    plan_excerpt: Dict[str, Any] = Field(default_factory=dict, description="计划摘录")
    artifacts_excerpt: Dict[str, Any] = Field(default_factory=dict, description="artifacts摘录")
    limits: Dict[str, Any] = Field(default_factory=dict, description="限制信息")
    model: Dict[str, str] = Field(default_factory=dict, description="使用的模型信息")
    hash: str = Field(..., description="查询+计划的稳定哈希")

    def to_jsonl(self) -> str:
        """转换为JSONL格式"""
        return json.dumps(self.dict(), ensure_ascii=False, separators=(',', ':'))


class TelemetryLogger:
    """Telemetry日志记录器"""

    def __init__(self, log_file: str = "logs/telemetry.jsonl"):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

        # 统计信息
        self.stats = {
            "total_events": 0,
            "events_by_type": {},
            "events_by_stage": {}
        }

        logger.info(f"Telemetry日志记录器初始化: {self.log_file}")

    def log_event(self,
                  stage: TelemetryStage,
                  event: TelemetryEvent,
                  user_query: str,
                  request_id: Optional[str] = None,
                  context: Optional[Dict[str, Any]] = None,
                  plan_excerpt: Optional[Dict[str, Any]] = None,
                  artifacts_excerpt: Optional[Dict[str, Any]] = None,
                  limits: Optional[Dict[str, Any]] = None,
                  model: Optional[Dict[str, str]] = None) -> str:
        """
        记录一个telemetry事件

        Args:
            stage: 执行阶段
            event: 事件类型
            user_query: 用户查询
            request_id: 请求ID，如果不提供则自动生成
            context: 事件上下文
            plan_excerpt: 计划摘录
            artifacts_excerpt: artifacts摘录
            limits: 限制信息
            model: 模型信息

        Returns:
            生成的request_id
        """
        if request_id is None:
            request_id = str(uuid.uuid4())

        # 生成查询+计划的哈希
        hash_content = f"{user_query}|{json.dumps(plan_excerpt or {}, sort_keys=True)}"
        content_hash = hashlib.sha256(hash_content.encode()).hexdigest()[:16]

        # 创建记录
        record = TelemetryRecord(
            ts=datetime.now(timezone.utc).isoformat(),
            request_id=request_id,
            stage=stage,
            event=event,
            user_query=user_query,
            context=context or {},
            plan_excerpt=plan_excerpt or {},
            artifacts_excerpt=artifacts_excerpt or {},
            limits=limits or {},
            model=model or {},
            hash=content_hash
        )

        # 线程安全写入
        with self._lock:
            try:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(record.to_jsonl() + '\n')
                    f.flush()

                # 更新统计信息
                self.stats["total_events"] += 1
                self.stats["events_by_type"][event] = self.stats["events_by_type"].get(event, 0) + 1
                self.stats["events_by_stage"][stage] = self.stats["events_by_stage"].get(stage, 0) + 1

                logger.debug(f"Telemetry事件已记录: {stage.value}/{event.value}")

            except Exception as e:
                logger.error(f"写入telemetry日志失败: {e}")

        return request_id

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return self.stats.copy()

    def search_events(self,
                     event_type: Optional[TelemetryEvent] = None,
                     stage: Optional[TelemetryStage] = None,
                     request_id: Optional[str] = None,
                     limit: int = 100) -> List[TelemetryRecord]:
        """
        搜索telemetry事件

        Args:
            event_type: 事件类型过滤
            stage: 阶段过滤
            request_id: 请求ID过滤
            limit: 返回记录数量限制

        Returns:
            匹配的记录列表
        """
        results = []

        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if len(results) >= limit:
                        break

                    try:
                        data = json.loads(line.strip())
                        record = TelemetryRecord(**data)

                        # 应用过滤条件
                        if event_type and record.event != event_type:
                            continue
                        if stage and record.stage != stage:
                            continue
                        if request_id and record.request_id != request_id:
                            continue

                        results.append(record)

                    except Exception as e:
                        logger.warning(f"解析telemetry记录失败: {e}")
                        continue

        except FileNotFoundError:
            logger.warning(f"Telemetry日志文件不存在: {self.log_file}")
        except Exception as e:
            logger.error(f"读取telemetry日志失败: {e}")

        return results

    def get_request_events(self, request_id: str) -> List[TelemetryRecord]:
        """获取特定请求的所有事件"""
        return self.search_events(request_id=request_id, limit=1000)


# 全局telemetry实例
_telemetry_instance = None
_telemetry_lock = threading.Lock()


def get_telemetry_logger() -> TelemetryLogger:
    """获取全局telemetry记录器实例"""
    global _telemetry_instance

    if _telemetry_instance is None:
        with _telemetry_lock:
            if _telemetry_instance is None:
                _telemetry_instance = TelemetryLogger()

    return _telemetry_instance
