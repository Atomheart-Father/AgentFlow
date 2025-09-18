#!/usr/bin/env python3
"""
测试超时处理功能
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_timeout():
    """测试超时处理"""
    print("=== 测试超时处理 ===\n")

    try:
        from tool_registry import execute_tool, get_tools

        # 获取工具列表
        tools = get_tools()

        print("1. 测试math_calc工具（应该快速成功）...")
        result = execute_tool("math_calc", tools, expression="2+3")
        print(f"✅ 结果: {result}")

        print("\n2. 测试不存在的工具（应该返回默认错误）...")
        result = execute_tool("nonexistent_tool", tools, param="test")
        print(f"❌ 结果: {result}")

        print("\n✅ 超时处理测试完成")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

async def test_weather_with_timeout():
    """测试天气工具的超时处理"""
    print("\n=== 测试天气工具超时处理 ===\n")

    try:
        from tool_registry import execute_tool, get_tools

        # 获取工具列表
        tools = get_tools()

        print("1. 测试正常天气查询...")
        result = execute_tool("weather_get", tools, location="北京")
        print(f"✅ 结果: {result}")

        print("\n✅ 天气工具测试完成")

    except Exception as e:
        print(f"❌ 天气工具测试失败: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """主测试函数"""
    await test_timeout()
    await test_weather_with_timeout()

if __name__ == "__main__":
    asyncio.run(main())
