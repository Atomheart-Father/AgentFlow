"""
网页搜索工具 - 使用DuckDuckGo搜索
"""

from typing import Dict, Any, List
import asyncio
from datetime import datetime


class ToolWebSearch:
    """网页搜索工具"""

    def __init__(self):
        self.name = "web.search"
        self.description = "使用DuckDuckGo进行网页搜索，返回搜索结果摘要"
        self.parameters = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询关键词"
                },
                "limit": {
                    "type": "integer",
                    "description": "返回的最大结果数量，默认5",
                    "default": 5
                },
                "region": {
                    "type": "string",
                    "description": "搜索区域，如'wt-wt'表示全球，'us-en'表示美国英语",
                    "default": "wt-wt"
                }
            },
            "required": ["query"]
        }

    async def _search_duckduckgo(self, query: str, limit: int = 5, region: str = "wt-wt") -> List[Dict[str, Any]]:
        """
        使用DuckDuckGo进行搜索

        Args:
            query: 搜索查询
            limit: 结果数量限制
            region: 搜索区域

        Returns:
            搜索结果列表
        """
        try:
            from duckduckgo_search import DDGS

            results = []
            with DDGS() as ddgs:
                # 使用text搜索
                search_results = list(ddgs.text(
                    query,
                    region=region,
                    max_results=limit
                ))

            # 格式化结果
            for i, result in enumerate(search_results[:limit]):
                formatted_result = {
                    "title": result.get("title", ""),
                    "url": result.get("href", ""),
                    "snippet": result.get("body", ""),
                    "rank": i + 1
                }
                results.append(formatted_result)

            return results

        except ImportError:
            raise ValueError("duckduckgo-search库未安装，请运行: pip install duckduckgo-search")
        except Exception as e:
            raise ValueError(f"DuckDuckGo搜索失败: {e}")

    async def _search_mock(self, query: str, limit: int = 5, region: str = "wt-wt") -> List[Dict[str, Any]]:
        """
        模拟搜索结果（当DuckDuckGo不可用时使用）

        Args:
            query: 搜索查询
            limit: 结果数量限制
            region: 搜索区域

        Returns:
            模拟搜索结果
        """
        # 模拟搜索结果
        mock_results = [
            {
                "title": f"{query} - 官方文档",
                "url": f"https://example.com/docs/{query.replace(' ', '-')}",
                "snippet": f"这是关于{query}的官方文档和指南。",
                "rank": 1
            },
            {
                "title": f"{query} 教程",
                "url": f"https://example.com/tutorial/{query.replace(' ', '-')}",
                "snippet": f"学习{query}的完整教程，包括基础概念和高级用法。",
                "rank": 2
            },
            {
                "title": f"{query} 最佳实践",
                "url": f"https://example.com/best-practices/{query.replace(' ', '-')}",
                "snippet": f"{query}的最佳实践和使用建议。",
                "rank": 3
            }
        ]

        return mock_results[:limit]

    async def run(self, query: str, limit: int = 5, region: str = "wt-wt", **kwargs) -> Dict[str, Any]:
        """
        执行网页搜索

        Args:
            query: 搜索查询
            limit: 最大结果数量
            region: 搜索区域
            **kwargs: 其他参数

        Returns:
            搜索结果
        """
        try:
            # 尝试使用DuckDuckGo搜索
            try:
                results = await self._search_duckduckgo(query, limit, region)
                search_engine = "DuckDuckGo"
            except Exception:
                # 如果DuckDuckGo失败，使用模拟结果
                results = await self._search_mock(query, limit, region)
                search_engine = "Mock (DuckDuckGo unavailable)"

            result = {
                "query": query,
                "search_engine": search_engine,
                "region": region,
                "total_results": len(results),
                "results": results,
                "timestamp": datetime.now().isoformat()
            }

            return result

        except Exception as e:
            raise ValueError(f"网页搜索失败: {e}")
