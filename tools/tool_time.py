"""
时间工具 - 获取当前时间信息
"""

from datetime import datetime, timezone
from typing import Dict, Any


class ToolTime:
    """时间工具"""

    def __init__(self):
        self.name = "time_now"
        self.description = "获取当前时间信息，包括ISO格式时间、时区、相对时间描述"
        self.parameters = {
            "type": "object",
            "properties": {},
            "required": []
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """
        获取当前时间信息

        Returns:
            Dict包含时间信息
        """
        now = datetime.now(timezone.utc)
        local_now = now.astimezone()

        # 获取相对时间描述
        hour = local_now.hour
        if 5 <= hour < 12:
            time_of_day = "上午"
        elif 12 <= hour < 18:
            time_of_day = "下午"
        elif 18 <= hour < 22:
            time_of_day = "晚上"
        else:
            time_of_day = "深夜"

        result = {
            "iso_time": now.isoformat(),
            "local_time": local_now.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "timezone": local_now.tzname(),
            "timestamp": int(now.timestamp()),
            "time_of_day": time_of_day,
            "weekday": local_now.strftime("%A"),  # 星期几
            "date": local_now.strftime("%Y-%m-%d")
        }

        return result
