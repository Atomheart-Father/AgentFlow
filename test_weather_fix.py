#!/usr/bin/env python3
"""
测试天气工具和参数映射修复
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_weather_direct():
    """直接测试天气工具"""
    print("=== 直接测试天气工具 ===\n")

    try:
        from tools.tool_weather import ToolWeather
        from tool_registry import execute_tool, get_tools

        # 创建天气工具实例
        weather_tool = ToolWeather()

        # 测试直接调用
        print("1. 测试直接调用天气工具...")
        result = await weather_tool.run(location="北京")
        print(f"✅ 天气工具调用成功: {result}")

    except Exception as e:
        print(f"❌ 天气工具直接调用失败: {e}")
        import traceback
        traceback.print_exc()

async def test_parameter_mapping():
    """测试参数映射"""
    print("\n=== 测试参数映射 ===\n")

    try:
        from orchestrator.executor import Executor

        # 创建执行器
        executor = Executor()

        # 测试参数映射
        print("1. 测试参数映射逻辑...")
        test_inputs = {"city": "用户所在城市（假设为默认城市，如北京）"}
        mapped = executor._map_tool_parameters("weather_get", test_inputs)
        print(f"原始参数: {test_inputs}")
        print(f"映射后参数: {mapped}")

        # 测试正常参数
        test_inputs2 = {"city": "上海"}
        mapped2 = executor._map_tool_parameters("weather_get", test_inputs2)
        print(f"正常参数映射: {test_inputs2} -> {mapped2}")

    except Exception as e:
        print(f"❌ 参数映射测试失败: {e}")
        import traceback
        traceback.print_exc()

async def test_tool_registry():
    """测试工具注册表"""
    print("\n=== 测试工具注册表 ===\n")

    try:
        from tool_registry import get_tools, execute_tool

        # 获取工具列表
        tools = get_tools()
        print(f"已加载工具数量: {len(tools)}")

        weather_tools = [t for t in tools if t.name == "weather_get"]
        if weather_tools:
            print("✅ 找到天气工具")
            print(f"工具类: {type(weather_tools[0])}")
            print(f"run方法: {weather_tools[0].run}")
            print(f"是否异步: {asyncio.iscoroutinefunction(weather_tools[0].run)}")
        else:
            print("❌ 未找到天气工具")

    except Exception as e:
        print(f"❌ 工具注册表测试失败: {e}")
        import traceback
        traceback.print_exc()

async def test_weather_via_registry():
    """通过注册表测试天气工具"""
    print("\n=== 通过注册表测试天气工具 ===\n")

    try:
        from tool_registry import execute_tool, get_tools

        # 获取工具列表
        tools = get_tools()

        # 测试execute_tool
        print("1. 测试execute_tool调用...")
        result = execute_tool("weather_get", tools, location="北京")
        print(f"✅ execute_tool调用成功: {result}")

    except Exception as e:
        print(f"❌ execute_tool调用失败: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """主测试函数"""
    await test_weather_direct()
    await test_parameter_mapping()
    await test_tool_registry()
    await test_weather_via_registry()

if __name__ == "__main__":
    asyncio.run(main())
