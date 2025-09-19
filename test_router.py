#!/usr/bin/env python3
"""
测试智能查询路由器
"""

from router import route_query, QueryType, explain_routing

def test_router():
    """测试路由器功能"""
    test_queries = [
        # 简单问答
        ("你好", QueryType.SIMPLE_CHAT),
        ("1+1等于几", QueryType.SIMPLE_CHAT),
        ("今天天气怎么样", QueryType.COMPLEX_PLAN),
        ("帮我查一下明天天气", QueryType.COMPLEX_PLAN),
        ("请分析这个数据", QueryType.COMPLEX_PLAN),
        ("/chat 你是谁", QueryType.SIMPLE_CHAT),
        ("/plan 制定学习计划", QueryType.COMPLEX_PLAN),

        # 复杂任务
        ("帮我写一个Python函数", QueryType.COMPLEX_PLAN),
        ("规划一下我的旅行", QueryType.COMPLEX_PLAN),
        ("搜索最新的AI新闻", QueryType.COMPLEX_PLAN),
        ("生成一个报告", QueryType.COMPLEX_PLAN),
    ]

    print("🧪 测试智能查询路由器")
    print("=" * 60)

    for query, expected in test_queries:
        query_type, metadata = route_query(query)
        explanation = explain_routing(query_type, metadata)

        status = "✅" if query_type == expected else "❌"
        expected_str = expected.value

        print(f"{status} 查询: {query}")
        print(f"   路由: {query_type.value} (期望: {expected_str})")
        print(f"   解释: {explanation}")
        print("-" * 60)

if __name__ == "__main__":
    test_router()
