"""
智能路由器 - 区分chat vs orchestrate模式
"""
import re
from typing import Dict, Any, Tuple
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class QueryType(Enum):
    """查询类型（向后兼容）"""
    SIMPLE_CHAT = "simple_chat"
    COMPLEX_PLAN = "complex_plan"


class RouteMode(Enum):
    """路由模式"""
    CHAT = "chat"
    ORCHESTRATE = "orchestrate"


class QueryRouter:
    """查询路由器"""

    def __init__(self):
        # 强制模式前缀
        self.force_chat_prefixes = ["/chat", "!chat", "chat:"]
        self.force_orchestrate_prefixes = ["/plan", "/orchestrate", "!plan", "!orchestrate", "plan:"]

        # Orchestrate关键词（需要复杂编排的场景）
        self.orchestrate_keywords = [
            # 时间相关
            "明天", "今天", "昨天", "日期", "时间", "几点", "什么时候",
            "date", "time", "tomorrow", "today", "yesterday", "when",

            # 文件操作
            "写", "保存", "创建", "写入", "导出", "保存到", "写到",
            "write", "save", "create", "export", "save to",

            # 工具调用
            "搜索", "查询", "查找", "计算", "计算器", "天气", "地图",
            "search", "query", "find", "calculate", "weather", "map",

            # RAG相关
            "文档", "知识库", "资料", "文件", "笔记",
            "document", "knowledge", "file", "note",

            # 复杂任务
            "规划", "计划", "安排", "组织", "整理",
            "plan", "schedule", "organize", "arrange",

            # 邮件相关
            "邮件", "邮箱", "发邮件", "收邮件",
            "email", "mail", "send", "receive",

            # 日历相关
            "日历", "日程", "会议", "提醒",
            "calendar", "schedule", "meeting", "reminder",

            # 网络操作
            "网页", "网站", "抓取", "爬取",
            "web", "website", "scrape", "crawl",

            # 数据处理
            "分析", "统计", "汇总", "报告",
            "analyze", "statistics", "summary", "report",

            # 多步骤任务
            "先", "然后", "接着", "最后", "步骤",
            "first", "then", "next", "finally", "step"
        ]

        # Chat关键词（简单对话场景）
        self.chat_keywords = [
            # 问候
            "你好", "您好", "hello", "hi", "hey",

            # 闲聊
            "怎么样", "如何", "什么", "为什么", "怎么",
            "how", "what", "why", "how",

            # 个人问题
            "你是谁", "你的名字", "介绍", "自我介绍",
            "who are you", "your name", "introduce",

            # 简单指令
            "帮我", "请", "麻烦", "能否",
            "help", "please", "can you",

            # 情感表达
            "谢谢", "感谢", "好的", "好的",
            "thank", "thanks", "ok", "good"
        ]

    def _check_force_mode(self, query: str) -> Tuple[RouteMode, str]:
        """检查是否强制指定模式"""
        query_lower = query.lower().strip()

        # 检查强制chat模式
        for prefix in self.force_chat_prefixes:
            if query_lower.startswith(prefix):
                clean_query = query[len(prefix):].strip()
                return RouteMode.CHAT, f"用户强制指定chat模式: {prefix}"

        # 检查强制orchestrate模式
        for prefix in self.force_orchestrate_prefixes:
            if query_lower.startswith(prefix):
                clean_query = query[len(prefix):].strip()
                return RouteMode.ORCHESTRATE, f"用户强制指定orchestrate模式: {prefix}"

        return None, query

    def _heuristic_route(self, query: str) -> Tuple[RouteMode, str]:
        """启发式路由"""
        query_lower = query.lower()

        # 计算orchestrate关键词匹配数
        orchestrate_score = 0
        for keyword in self.orchestrate_keywords:
            if keyword in query_lower:
                orchestrate_score += 1

        # 计算chat关键词匹配数
        chat_score = 0
        for keyword in self.chat_keywords:
            if keyword in query_lower:
                chat_score += 1

        # 查询长度因素（长查询更可能是复杂任务）
        query_length = len(query)

        # 决策逻辑
        if orchestrate_score > chat_score:
            return RouteMode.ORCHESTRATE, f"检测到{orchestrate_score}个编排关键词"
        elif orchestrate_score == 0 and chat_score > 0:
            return RouteMode.CHAT, f"检测到{chat_score}个对话关键词"
        elif query_length > 50:  # 长查询倾向于编排
            return RouteMode.ORCHESTRATE, f"长查询({query_length}字符)倾向于编排"
        elif query_length < 20:  # 短查询倾向于对话
            return RouteMode.CHAT, f"短查询({query_length}字符)倾向于对话"
        else:
            # 灰区：使用AI二分类
            try:
                return self._advanced_route(query)
            except Exception as e:
                logger.warning(f"AI二分类失败: {e}, 使用默认编排模式")
                return RouteMode.ORCHESTRATE, f"灰区查询，默认使用编排模式(安全优先)"

    def _advanced_route(self, query: str) -> Tuple[RouteMode, str]:
        """高级路由（使用小模型二分类）
        对灰区查询使用轻量级模型进行二分类
        """
        # 暂时使用启发式，避免asyncio.run()在已有循环中的问题
        # TODO: 在合适的地方实现异步AI分类
        logger.info("使用启发式路由（AI二分类暂未实现）")
        return self._heuristic_route(query)

    def route(self, query: str) -> Dict[str, Any]:
        """路由主函数"""
        if not query or not query.strip():
            return {
                "mode": RouteMode.CHAT.value,
                "reason": "空查询，使用chat模式"
            }

        # 1. 检查强制模式
        force_mode, clean_query = self._check_force_mode(query)
        if force_mode:
            return {
                "mode": force_mode.value,
                "reason": f"强制模式: {clean_query}",
                "original_query": query,
                "clean_query": clean_query
            }

        # 2. 高级路由（可配置）
        use_advanced = False  # 可以从配置读取
        if use_advanced:
            mode, reason = self._advanced_route(clean_query)
        else:
            mode, reason = self._heuristic_route(clean_query)

        return {
            "mode": mode.value,
            "reason": reason,
            "original_query": query,
            "clean_query": clean_query
        }


# 全局路由器实例
router = QueryRouter()


def route_query(query: str) -> Tuple[QueryType, Dict[str, Any]]:
    """便捷路由函数（向后兼容）"""
    result = router.route(query)

    # 映射新的RouteMode到旧的QueryType
    mode = result["mode"]
    if mode == RouteMode.CHAT.value:
        query_type = QueryType.SIMPLE_CHAT
    else:  # orchestrate
        query_type = QueryType.COMPLEX_PLAN

    return query_type, result


def explain_routing(query_type: QueryType, routing_metadata: Dict[str, Any]) -> str:
    """解释路由决策（向后兼容）"""
    if not routing_metadata:
        return "默认路由决策"

    reason = routing_metadata.get("reason", "未知原因")
    original_query = routing_metadata.get("original_query", "")
    clean_query = routing_metadata.get("clean_query", "")

    explanation = f"原因: {reason}"

    if original_query and clean_query and original_query != clean_query:
        explanation += f"\n原始查询: {original_query}"
        explanation += f"\n清理后: {clean_query}"

    return explanation