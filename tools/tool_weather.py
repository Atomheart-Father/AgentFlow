"""
天气查询工具 - 使用Open-Meteo免费API
"""

import httpx
from typing import Dict, Any, Optional
from datetime import datetime, timedelta


class ToolWeather:
    """天气查询工具"""

    def __init__(self):
        self.name = "weather_get"
        self.description = "获取指定城市的天气信息，支持经纬度或城市名查询"
        self.parameters = {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "位置信息，可以是城市名（如'北京'）或经纬度（如'39.9042,116.4074'）"
                },
                "date": {
                    "type": "string",
                    "description": "查询日期，格式为YYYY-MM-DD，默认为今天",
                    "default": datetime.now().strftime("%Y-%m-%d")
                }
            },
            "required": ["location"]
        }

        # 城市坐标映射（常用城市）
        self.city_coords = {
            "北京": (39.9042, 116.4074),
            "上海": (31.2304, 121.4737),
            "广州": (23.1291, 113.2644),
            "深圳": (22.5429, 114.0596),
            "杭州": (30.2741, 120.1551),
            "成都": (30.5728, 104.0668),
            "武汉": (30.5928, 114.3055),
            "南京": (32.0603, 118.7969),
            "西安": (34.3416, 108.9398),
            "重庆": (29.4316, 106.9123),
            "纽约": (40.7128, -74.0060),
            "伦敦": (51.5074, -0.1278),
            "东京": (35.6762, 139.6503),
            "巴黎": (48.8566, 2.3522),
        }

    def _parse_location(self, location: str) -> tuple[float, float]:
        """
        解析位置信息

        Args:
            location: 位置字符串

        Returns:
            (纬度, 经度) 元组
        """
        location = location.strip()

        # 尝试解析经纬度格式
        if ',' in location:
            try:
                parts = location.split(',')
                lat = float(parts[0].strip())
                lon = float(parts[1].strip())
                return lat, lon
            except ValueError:
                pass

        # 从城市映射中查找
        if location in self.city_coords:
            return self.city_coords[location]

        # 默认返回北京坐标
        return self.city_coords["北京"]

    def _get_weather_description(self, wmo_code: int) -> str:
        """
        根据WMO天气代码获取天气描述

        Args:
            wmo_code: WMO天气代码

        Returns:
            天气描述
        """
        weather_codes = {
            0: "晴朗",
            1: "主要晴朗",
            2: "局部多云",
            3: "阴天",
            45: "雾",
            48: "雾凇",
            51: "小雨",
            53: "中雨",
            55: "大雨",
            56: "冻雨",
            57: "冻雨",
            61: "小雨",
            63: "中雨",
            65: "大雨",
            66: "冻雨",
            67: "冻雨",
            71: "小雪",
            73: "中雪",
            75: "大雪",
            77: "雪粒",
            80: "小阵雨",
            81: "中阵雨",
            82: "大阵雨",
            85: "小阵雪",
            86: "大阵雪",
            95: "雷暴",
            96: "雷暴伴小冰雹",
            99: "雷暴伴大冰雹"
        }
        return weather_codes.get(wmo_code, f"未知天气代码: {wmo_code}")

    async def run(self, location: str, date: str = None, **kwargs) -> Dict[str, Any]:
        """
        查询天气信息

        Args:
            location: 位置信息
            date: 查询日期（可选）
            **kwargs: 其他参数

        Returns:
            天气信息
        """
        try:
            # 解析位置
            lat, lon = self._parse_location(location)

            # 设置查询日期
            if date is None:
                query_date = datetime.now().strftime("%Y-%m-%d")
            else:
                query_date = date

            # Open-Meteo API URL
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": lat,
                "longitude": lon,
                "current": ["temperature_2m", "weather_code"],
                "hourly": ["temperature_2m", "weather_code", "precipitation_probability"],
                "daily": ["temperature_2m_max", "temperature_2m_min", "weather_code"],
                "timezone": "auto",
                "forecast_days": 1
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

            # 解析结果
            current = data.get("current", {})
            daily = data.get("daily", {})
            hourly = data.get("hourly", {})

            if not current:
                raise ValueError("无法获取天气数据")

            result = {
                "location": location,
                "coordinates": {"lat": lat, "lon": lon},
                "query_date": query_date,
                "current": {
                    "temperature": current.get("temperature_2m"),
                    "weather_code": current.get("weather_code"),
                    "weather_description": self._get_weather_description(current.get("weather_code", 0)),
                    "time": current.get("time")
                }
            }

            # 添加每日预报
            if daily:
                result["daily"] = {
                    "max_temp": daily.get("temperature_2m_max", [None])[0],
                    "min_temp": daily.get("temperature_2m_min", [None])[0],
                    "weather_code": daily.get("weather_code", [None])[0],
                    "weather_description": self._get_weather_description(daily.get("weather_code", [0])[0])
                }

            return result

        except httpx.HTTPError as e:
            raise ValueError(f"天气API请求失败: {e}")
        except Exception as e:
            raise ValueError(f"天气查询失败: {e}")
