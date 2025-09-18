"""
日期归一化工具 - 将自然语言日期转换为标准格式
"""

import time
from datetime import datetime, timedelta
from typing import Optional
from dateutil import parser as date_parser
from dateutil.tz import gettz
from schemas.tool_result import StandardToolResult, ToolError, ErrorCode, create_tool_meta, create_tool_error


def normalize_date(date_str: str, tz: str = "UTC") -> str:
    """
    将自然语言日期转换为标准YYYY-MM-DD格式

    Args:
        date_str: 日期字符串，如 "tomorrow", "next Monday", "2024-01-15"
        tz: 时区，如 "Europe/Amsterdam", "UTC", "Asia/Shanghai"

    Returns:
        YYYY-MM-DD格式的日期字符串

    Raises:
        ValueError: 无法解析日期
    """
    try:
        # 获取时区
        timezone = gettz(tz) if tz != "UTC" else None

        # 解析日期
        if date_str.lower() in ["today", "今天"]:
            date_obj = datetime.now(timezone).date()
        elif date_str.lower() in ["tomorrow", "明天"]:
            date_obj = (datetime.now(timezone) + timedelta(days=1)).date()
        elif date_str.lower() in ["yesterday", "昨天"]:
            date_obj = (datetime.now(timezone) - timedelta(days=1)).date()
        elif date_str.lower() in ["day after tomorrow", "后天"]:
            date_obj = (datetime.now(timezone) + timedelta(days=2)).date()
        else:
            # 尝试解析其他格式
            try:
                # 先尝试直接解析
                date_obj = date_parser.parse(date_str, fuzzy=True).date()
            except:
                # 如果失败，尝试添加当前年份
                current_year = datetime.now().year
                try:
                    date_obj = date_parser.parse(f"{date_str} {current_year}", fuzzy=True).date()
                except:
                    raise ValueError(f"无法解析日期: {date_str}")

        return date_obj.strftime("%Y-%m-%d")

    except Exception as e:
        raise ValueError(f"日期解析失败: {str(e)}")


class ToolDateNormalizer:
    """日期归一化工具"""

    def __init__(self):
        self.name = "date_normalize"
        self.description = "将自然语言日期转换为标准YYYY-MM-DD格式"
        self.parameters = {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "要归一化的日期，支持自然语言如'tomorrow'、'next Monday'等"
                },
                "timezone": {
                    "type": "string",
                    "default": "UTC",
                    "description": "时区，如'Europe/Amsterdam'、'Asia/Shanghai'、'UTC'"
                }
            },
            "required": ["date"]
        }

    def run(self, date: str, timezone: str = "UTC") -> StandardToolResult:
        """
        归一化日期

        Args:
            date: 日期字符串
            timezone: 时区

        Returns:
            标准化的工具结果
        """
        start_time = time.time()

        try:
            normalized_date = normalize_date(date, timezone)

            latency_ms = int((time.time() - start_time) * 1000)
            meta = create_tool_meta(self.name, latency_ms, {
                "date": date,
                "timezone": timezone
            })

            return StandardToolResult.success({
                "normalized_date": normalized_date,
                "original_input": date,
                "timezone": timezone
            }, meta)

        except ValueError as e:
            latency_ms = int((time.time() - start_time) * 1000)
            error = create_tool_error(ErrorCode.INVALID_INPUT, str(e), retryable=False)
            meta = create_tool_meta(self.name, latency_ms, {
                "date": date,
                "timezone": timezone
            })
            return StandardToolResult.failure(error, meta)

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            error = create_tool_error(ErrorCode.INTERNAL, f"日期归一化失败: {str(e)}", retryable=True)
            meta = create_tool_meta(self.name, latency_ms, {
                "date": date,
                "timezone": timezone
            })
            return StandardToolResult.failure(error, meta)
