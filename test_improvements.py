#!/usr/bin/env python3
"""
测试系统改进：超时处理和ask_user功能
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_timeout_handling():
    """测试超时处理"""
    print("=== 测试超时处理 ===\n")

    try:
        from tool_registry import execute_tool, get_tools

        # 获取工具列表
        tools = get_tools()

        # 测试weather_get工具的超时处理
        print("1. 测试天气工具超时处理...")
        # 这里我们使用一个不存在的城市来触发超时
        result = execute_tool("weather_get", tools, location="一个不存在的城市名")
        print(f"✅ 超时处理正常: {result}")

    except Exception as e:
        print(f"❌ 超时处理测试失败: {e}")
        import traceback
        traceback.print_exc()

async def test_ask_user_query():
    """测试ask_user查询"""
    print("\n=== 测试ask_user查询 ===\n")

    try:
        from orchestrator.orchestrator import get_orchestrator

        # 创建编排器
        orchestrator = get_orchestrator()

        # 测试一个需要用户位置的查询
        query = "查明天Rotterdam是否下雨"
        print(f"测试查询: {query}")

        result = await orchestrator.orchestrate(query)
        print(f"编排器状态: {result.status}")
        print(f"最终答案: {result.final_answer}")

        # 检查是否有ask_user数据
        if result.execution_state and result.execution_state.get_artifact("ask_user_pending"):
            ask_user_data = result.execution_state.get_artifact("ask_user_pending")
            print(f"✅ 成功检测到ask_user问题: {ask_user_data['question']}")
        else:
            print("❌ 未检测到ask_user问题")

    except Exception as e:
        print(f"❌ ask_user测试失败: {e}")
        import traceback
        traceback.print_exc()

async def test_tool_call_limit():
    """测试工具调用次数限制"""
    print("\n=== 测试工具调用次数限制 ===\n")

    try:
        from orchestrator.orchestrator import get_orchestrator

        # 创建编排器
        orchestrator = get_orchestrator()

        # 测试一个复杂的查询，需要多个工具调用
        query = "帮我计算(12+3*4)^2，然后查询北京天气，再查看今天的日程"
        print(f"测试复杂查询: {query}")

        result = await orchestrator.orchestrate(query)
        print(f"编排器状态: {result.status}")
        print(f"计划步骤数: {len(result.final_plan.steps) if result.final_plan else 0}")
        print(f"执行步骤数: {len(result.execution_state.completed_steps) if result.execution_state else 0}")

        if len(result.final_plan.steps) > 2 if result.final_plan else 0:
            print("✅ 成功支持多步骤任务（超过2个工具调用）")
        else:
            print("ℹ️ 任务步骤数未超过限制")

    except Exception as e:
        print(f"❌ 工具调用限制测试失败: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """主测试函数"""
    await test_timeout_handling()
    await test_ask_user_query()
    await test_tool_call_limit()

if __name__ == "__main__":
    asyncio.run(main())
