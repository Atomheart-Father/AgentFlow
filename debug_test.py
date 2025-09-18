#!/usr/bin/env python3
"""
调试工具调用功能的测试脚本
"""

import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_tools():
    """测试工具调用功能"""
    print("=== 工具调用功能调试测试 ===\n")

    try:
        # 1. 测试配置
        from config import get_config
        config = get_config()
        print("✅ 配置加载成功")
        print(f"   模型提供商: {config.model_provider}")
        print(f"   工具功能: {'启用' if config.tools_enabled else '禁用'}")
        print(f"   DeepSeek模型: {getattr(config, 'deepseek_model', '默认')}")

        # 2. 测试工具注册
        print("\n--- 测试工具注册 ---")
        from tool_registry import get_tools, execute_tool, to_openai_tools

        tools = get_tools()
        print("✅ 工具注册成功")
        print(f"   工具数量: {len(tools)}")
        print(f"   工具名称: {[t.name for t in tools]}")

        # 3. 测试单个工具调用
        print("\n--- 测试 time_now 工具 ---")
        result = execute_tool("time_now", tools)
        print("✅ time_now工具执行成功")
        print(f"   结果: {result}")

        # 4. 测试LLM接口
        print("\n--- 测试 LLM 接口 ---")
        from llm_interface import create_llm_interface_with_keys

        llm = create_llm_interface_with_keys()
        print("✅ LLM接口创建成功")
        print(f"   提供者类型: {type(llm.provider)}")

        # 5. 测试简单生成
        print("\n--- 测试简单文本生成 ---")
        simple_result = await llm.generate("Hello, how are you?")
        print("✅ 简单生成成功")
        print(f"   响应: {simple_result.content[:100]}...")

        # 6. 测试AgentCore（使用已创建的LLM实例）
        print("\n--- 测试 AgentCore ---")
        from agent_core import AgentCore

        agent = AgentCore(llm_interface=llm)  # 使用已创建的LLM实例
        print("✅ AgentCore创建成功")
        print(f"   工具数量: {len(agent.tools)}")

        # 7. 直接测试LLM工具调用（绕过AgentCore）
        print("\n--- 直接测试LLM工具调用 ---")

        # 构建工具schema
        from tool_registry import to_openai_tools
        tools_schema = to_openai_tools(agent.tools)

        # 构建消息
        messages = [
            {"role": "system", "content": "You are a helpful assistant. Use tools when needed."},
            {"role": "user", "content": "What time is it now?"}
        ]

        # 测试直接LLM工具调用
        try:
            tool_result = await llm.generate(
                messages=messages,
                tools_schema=tools_schema
            )
            print("✅ 直接LLM调用完成")
            print(f"   响应: {tool_result.content[:200]}...")
            print(f"   是否有工具调用: {tool_result.function_calls is not None}")
            if tool_result.function_calls:
                print(f"   工具调用详情: {tool_result.function_calls}")
            else:
                print("   ❌ 没有触发工具调用")
        except Exception as e:
            print(f"❌ 直接LLM调用失败: {e}")
            print("   跳过工具调用详情")

        # 8. 测试AgentCore（简化系统提示词）
        print("\n--- 测试AgentCore（简化提示词） ---")

        # 创建更简单的系统提示词
        simple_agent = AgentCore(llm_interface=llm)
        simple_agent._build_system_prompt = lambda: "You are a helpful assistant. For time questions, call time_now tool."

        simple_result = await simple_agent.process("What time is it now?")
        print("✅ 简化AgentCore测试完成")
        print(f"   响应: {simple_result['response'][:200]}...")
        print(f"   工具调用轨迹: {simple_result['metadata'].get('tool_call_trace', [])}")

        print("\n🎉 所有测试通过！")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_tools())
