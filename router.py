"""
智能查询路由器 - 区分简单问答和复杂编排任务
实现零开销启发式路由 + 可选LLM兜底分类
"""

import re
from typing import Dict, Any, Tuple
from enum import Enum


class QueryType(Enum):
    """查询类型枚举"""
    SIMPLE_CHAT = "simple"      # 简单问答，直接用Chat模型
    COMPLEX_PLAN = "complex"    # 复杂任务，需要Planner→Executor→Judge


class QueryRouter:
    """智能查询路由器"""

    def __init__(self):
        # 复杂任务的关键词模式
        self.complex_patterns = [
            # 时序相关
            r'\b(?:明天|后天|今天|昨天|前天|下周|上周|明年|去年|日期|时间|几号|星期|周几)\b',
            r'\b(?:tomorrow|yesterday|next week|last week|date|time|schedule)\b',

            # 天气相关
            r'\b(?:天气|气温|降雨|下雨|晴天|阴天|多云|雨天|雪|风)\b',
            r'\b(?:weather|temperature|rain|sunny|cloudy|wind)\b',

            # 规划和任务相关
            r'\b(?:计划|规划|安排|步骤|执行|完成|总结|分析)\b',
            r'\b(?:plan|schedule|arrange|steps|execute|complete|summary|analyze)\b',

            # 文件操作相关
            r'\b(?:生成文件|保存|写入|创建|写到桌面|md|txt|json|文档)\b',
            r'\b(?:generate file|save|write|create|markdown|text|json)\b',

            # 工具调用相关
            r'\b(?:搜索|查找|计算|换算|邮件|日历|工具|RAG|引用)\b',
            r'\b(?:search|find|calculate|convert|email|calendar|tool)\b',

            # 复杂指令
            r'\b(?:帮我|请|需要|要求|必须|应该)\b.*\b(?:查|找|做|写|算|分析)\b',
            r'\b(?:help me|please|need|require|must|should)\b.*\b(?:check|find|do|write|calculate|analyze)\b',
        ]

        # 简单问答的否定模式（如果匹配这些，仍然走复杂流程）
        self.force_complex_patterns = [
            r'/plan\b',  # 强制编排
            r'/complex\b',
        ]

        # 强制简单问答的模式
        self.force_simple_patterns = [
            r'/chat\b',  # 强制直答
            r'/simple\b',
        ]

    def route_query(self, query: str, use_llm_fallback: bool = False) -> Tuple[QueryType, Dict[str, Any]]:
        """
        路由查询到合适的处理路径

        Args:
            query: 用户查询
            use_llm_fallback: 是否使用LLM兜底分类

        Returns:
            (QueryType, metadata)
        """

        # 1. 检查强制模式
        for pattern in self.force_simple_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                return QueryType.SIMPLE_CHAT, {"reason": "force_simple", "pattern": pattern}

        for pattern in self.force_complex_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                return QueryType.COMPLEX_PLAN, {"reason": "force_complex", "pattern": pattern}

        # 2. 快速启发式路由
        heuristic_result = self._heuristic_route(query)
        if heuristic_result:
            return heuristic_result

        # 3. LLM兜底路由（可选）
        if use_llm_fallback:
            return self._llm_route(query)

        # 4. 默认走简单模式
        return QueryType.SIMPLE_CHAT, {"reason": "default_simple"}

    def _heuristic_route(self, query: str) -> Tuple[QueryType, Dict[str, Any]] | None:
        """
        基于关键词的快速启发式路由

        Returns:
            如果能确定类型则返回，否则返回None
        """

        query_lower = query.lower().strip()
        query_length = len(query)

        # 检查是否匹配复杂任务模式
        for pattern in self.complex_patterns:
            if re.search(pattern, query_lower):
                return QueryType.COMPLEX_PLAN, {
                    "reason": "keyword_match",
                    "pattern": pattern,
                    "confidence": 0.8
                }

        # 基于长度和指令性的简单判断
        has_instruction_words = any(word in query_lower for word in [
            '帮我', '请', '需要', '要求', '必须', '应该', '分析', '计算', '查找', '搜索',
            'help', 'please', 'need', 'require', 'must', 'should', 'analyze', 'calculate', 'find', 'search'
        ])

        # 短查询且无指令性词语 -> 简单问答
        if query_length < 80 and not has_instruction_words:
            return QueryType.SIMPLE_CHAT, {
                "reason": "short_simple",
                "length": query_length,
                "has_instruction": has_instruction_words,
                "confidence": 0.7
            }

        # 长查询或有指令性词语 -> 复杂任务
        if query_length >= 80 or has_instruction_words:
            return QueryType.COMPLEX_PLAN, {
                "reason": "long_complex",
                "length": query_length,
                "has_instruction": has_instruction_words,
                "confidence": 0.6
            }

        # 无法确定，返回None使用兜底策略
        return None

    def _llm_route(self, query: str) -> Tuple[QueryType, Dict[str, Any]]:
        """
        使用LLM进行兜底路由分类
        注意：这里只是接口，实际实现需要LLM调用
        """
        # TODO: 实现LLM分类逻辑
        # 这里可以调用一个轻量级模型进行二分类

        return QueryType.SIMPLE_CHAT, {
            "reason": "llm_fallback",
            "confidence": 0.5
        }

    def explain_routing(self, query_type: QueryType, metadata: Dict[str, Any]) -> str:
        """解释路由决策原因"""
        reason = metadata.get("reason", "unknown")

        explanations = {
            "force_simple": "检测到强制简单模式标记",
            "force_complex": "检测到强制复杂模式标记",
            "keyword_match": "匹配到复杂任务关键词",
            "short_simple": "短查询，无复杂指令",
            "long_complex": "长查询或包含复杂指令",
            "llm_fallback": "LLM分类结果",
            "default_simple": "默认简单模式"
        }

        explanation = explanations.get(reason, f"未知原因: {reason}")

        if "pattern" in metadata:
            explanation += f" (匹配模式: {metadata['pattern']})"

        if "confidence" in metadata:
            explanation += f" (置信度: {metadata['confidence']:.1f})"

        return explanation


# 全局路由器实例
query_router = QueryRouter()


def route_query(query: str, use_llm_fallback: bool = False) -> Tuple[QueryType, Dict[str, Any]]:
    """
    便捷函数：路由查询

    Args:
        query: 用户查询
        use_llm_fallback: 是否使用LLM兜底

    Returns:
        (QueryType, metadata)
    """
    return query_router.route_query(query, use_llm_fallback)


def explain_routing(query_type: QueryType, metadata: Dict[str, Any]) -> str:
    """便捷函数：解释路由决策"""
    return query_router.explain_routing(query_type, metadata)


if __name__ == "__main__":
    # 测试路由器
    test_queries = [
        "你好",
        "帮我查一下明天天气",
        "1+1等于几",
        "/chat 你是谁",
        "/plan 帮我制定学习计划",
        "请分析一下这个数据",
        "今天天气怎么样",
        "帮我写一个Python函数计算斐波那契数列"
    ]

    for query in test_queries:
        query_type, metadata = route_query(query)
        explanation = explain_routing(query_type, metadata)
        print(f"查询: {query}")
        print(f"路由: {query_type.value} - {explanation}")
        print("-" * 50)
