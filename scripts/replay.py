#!/usr/bin/env python3
"""
Replay script for AgentFlow Telemetry v1
重放特定请求以便调试和A/B测试

Usage:
    python scripts/replay.py <request_id> [--dry-run] [--compare-with <other_request_id>]

Arguments:
    request_id: 要重放的请求ID
    --dry-run: 只显示重放信息，不实际执行
    --compare-with: 与另一个请求进行比较分析
"""

import sys
import json
import argparse
from typing import Dict, Any, Optional
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from telemetry import get_telemetry_logger, TelemetryRecord
from orchestrator import orchestrate_query
from logger import get_logger

logger = get_logger()


class ReplayEngine:
    """重放引擎"""

    def __init__(self):
        self.telemetry = get_telemetry_logger()

    def find_request_data(self, request_id: str) -> Optional[Dict[str, Any]]:
        """
        从telemetry日志中查找请求数据

        Args:
            request_id: 请求ID

        Returns:
            请求的完整数据或None
        """
        events = self.telemetry.get_request_events(request_id)
        if not events:
            return None

        # 重建请求上下文
        request_data = {
            "request_id": request_id,
            "user_query": "",
            "events": [],
            "plan": None,
            "artifacts": {},
            "models": {},
            "final_result": None
        }

        for event in events:
            request_data["events"].append(event.dict())

            # 提取关键信息
            if not request_data["user_query"]:
                request_data["user_query"] = event.user_query

            if event.plan_excerpt and not request_data["plan"]:
                request_data["plan"] = event.plan_excerpt

            if event.artifacts_excerpt:
                request_data["artifacts"].update(event.artifacts_excerpt)

            if event.model:
                request_data["models"].update(event.model)

        return request_data

    def replay_request(self, request_id: str, dry_run: bool = False) -> Dict[str, Any]:
        """
        重放请求

        Args:
            request_id: 请求ID
            dry_run: 是否只显示信息不执行

        Returns:
            重放结果
        """
        logger.info(f"开始重放请求: {request_id}")

        # 查找原始请求数据
        original_data = self.find_request_data(request_id)
        if not original_data:
            raise ValueError(f"找不到请求数据: {request_id}")

        logger.info(f"原始查询: {original_data['user_query']}")
        logger.info(f"事件数量: {len(original_data['events'])}")
        logger.info(f"使用的模型: {original_data['models']}")

        if dry_run:
            return {
                "status": "dry_run",
                "original_data": original_data,
                "message": "仅显示重放信息，未实际执行"
            }

        # 执行重放
        try:
            logger.info("开始执行重放...")

            # 使用相同的查询重新执行
            result = await orchestrate_query(
                user_query=original_data["user_query"],
                context={"replay": True, "original_request_id": request_id}
            )

            replay_result = {
                "status": "completed",
                "original_data": original_data,
                "replay_result": result.to_dict(),
                "comparison": self._compare_results(original_data, result.to_dict())
            }

            logger.info("重放完成")
            return replay_result

        except Exception as e:
            logger.error(f"重放失败: {e}")
            return {
                "status": "failed",
                "original_data": original_data,
                "error": str(e)
            }

    def _compare_results(self, original: Dict[str, Any], replay: Dict[str, Any]) -> Dict[str, Any]:
        """
        比较原始结果和重放结果

        Args:
            original: 原始数据
            replay: 重放结果

        Returns:
            比较分析
        """
        comparison = {
            "query_match": original["user_query"] == (replay.get("final_answer") or ""),
            "status_match": True,  # 假设重放成功
            "differences": []
        }

        # 比较状态
        if original.get("final_result", {}).get("status") != replay.get("status"):
            comparison["status_match"] = False
            comparison["differences"].append({
                "type": "status",
                "original": original.get("final_result", {}).get("status"),
                "replay": replay.get("status")
            })

        # 比较工具调用次数
        orig_tool_calls = original.get("final_result", {}).get("tool_calls", 0)
        replay_tool_calls = replay.get("total_tool_calls", 0)
        if orig_tool_calls != replay_tool_calls:
            comparison["differences"].append({
                "type": "tool_calls",
                "original": orig_tool_calls,
                "replay": replay_tool_calls
            })

        return comparison

    def compare_requests(self, request_id1: str, request_id2: str) -> Dict[str, Any]:
        """
        比较两个请求

        Args:
            request_id1: 第一个请求ID
            request_id2: 第二个请求ID

        Returns:
            比较结果
        """
        data1 = self.find_request_data(request_id1)
        data2 = self.find_request_data(request_id2)

        if not data1 or not data2:
            return {"error": "一个或两个请求ID不存在"}

        return {
            "request1": data1,
            "request2": data2,
            "comparison": {
                "query_same": data1["user_query"] == data2["user_query"],
                "model_same": data1["models"] == data2["models"],
                "event_count_diff": len(data1["events"]) - len(data2["events"])
            }
        }


def main():
    parser = argparse.ArgumentParser(description="AgentFlow Telemetry Replay Tool")
    parser.add_argument("request_id", help="要重放的请求ID")
    parser.add_argument("--dry-run", action="store_true", help="只显示重放信息，不实际执行")
    parser.add_argument("--compare-with", help="与另一个请求进行比较")

    args = parser.parse_args()

    engine = ReplayEngine()

    try:
        if args.compare_with:
            # 比较模式
            result = engine.compare_requests(args.request_id, args.compare_with)
            print(json.dumps(result, ensure_ascii=False, indent=2))

        else:
            # 重放模式
            import asyncio
            result = asyncio.run(engine.replay_request(args.request_id, args.dry_run))
            print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as e:
        logger.error(f"Replay failed: {e}")
        print(json.dumps({"error": str(e)}, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
