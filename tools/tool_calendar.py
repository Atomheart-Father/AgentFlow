"""
日程查询工具 - 从本地日程文件读取
"""

import json
from typing import Dict, Any, List
from pathlib import Path
from datetime import datetime, date


class ToolCalendar:
    """日程查询工具"""

    def __init__(self):
        self.name = "calendar_read"
        self.description = "从本地日程文件中读取日程信息，支持按日期范围过滤"
        self.parameters = {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "开始日期，格式为YYYY-MM-DD，默认为今天"
                },
                "end_date": {
                    "type": "string",
                    "description": "结束日期，格式为YYYY-MM-DD，默认为start_date"
                },
                "limit": {
                    "type": "integer",
                    "description": "返回的最大日程数量，默认10",
                    "default": 10
                }
            },
            "required": []
        }

        # 日程数据文件路径
        self.data_file = Path(__file__).parent.parent / "data" / "calendar.json"
        self._ensure_data_file()

    def _ensure_data_file(self):
        """确保数据文件存在"""
        self.data_file.parent.mkdir(parents=True, exist_ok=True)

        if not self.data_file.exists():
            # 创建示例数据
            sample_data = [
                {
                    "id": 1,
                    "title": "项目会议",
                    "start": "2025-01-20T10:00:00",
                    "end": "2025-01-20T11:30:00",
                    "location": "会议室A",
                    "notes": "讨论Q1项目计划"
                },
                {
                    "id": 2,
                    "title": "客户拜访",
                    "start": "2025-01-21T14:00:00",
                    "end": "2025-01-21T16:00:00",
                    "location": "客户公司",
                    "notes": "商务洽谈"
                },
                {
                    "id": 3,
                    "title": "团队建设",
                    "start": "2025-01-25T09:00:00",
                    "end": "2025-01-25T17:00:00",
                    "location": "市郊度假村",
                    "notes": "年度团队建设活动"
                }
            ]

            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(sample_data, f, indent=2, ensure_ascii=False)

    def _load_calendar_data(self) -> List[Dict[str, Any]]:
        """加载日程数据"""
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            raise ValueError(f"加载日程数据失败: {e}")

    def _parse_date(self, date_str: str) -> date:
        """解析日期字符串"""
        try:
            if 'T' in date_str:
                # 包含时间的格式
                return datetime.fromisoformat(date_str.replace('Z', '+00:00')).date()
            else:
                # 纯日期格式
                return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"无效的日期格式: {date_str}")

    def run(self, start_date: str = None, end_date: str = None, limit: int = 10, **kwargs) -> Dict[str, Any]:
        """
        查询日程信息

        Args:
            start_date: 开始日期
            end_date: 结束日期
            limit: 最大返回数量
            **kwargs: 其他参数

        Returns:
            日程信息
        """
        try:
            # 设置默认日期
            if start_date is None:
                start_date = datetime.now().strftime("%Y-%m-%d")
            if end_date is None:
                end_date = start_date

            start = self._parse_date(start_date)
            end = self._parse_date(end_date)

            if start > end:
                raise ValueError("开始日期不能晚于结束日期")

            # 加载数据
            all_events = self._load_calendar_data()

            # 过滤日期范围内的日程
            filtered_events = []
            for event in all_events:
                event_date = self._parse_date(event["start"])
                if start <= event_date <= end:
                    filtered_events.append(event)

            # 按开始时间排序
            filtered_events.sort(key=lambda x: x["start"])

            # 限制数量
            filtered_events = filtered_events[:limit]

            result = {
                "query": {
                    "start_date": start_date,
                    "end_date": end_date,
                    "limit": limit
                },
                "total_found": len(filtered_events),
                "events": filtered_events
            }

            return result

        except Exception as e:
            raise ValueError(f"日程查询失败: {e}")
