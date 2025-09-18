#!/usr/bin/env python3
"""
模型切换演示脚本
展示Gemini和DeepSeek两个模型的切换使用
"""
import asyncio
from llm_interface import LLMInterface
from config import get_config
from logger import setup_logging

# 初始化日志
setup_logging("INFO")


async def demo_model_switching():
    """演示模型切换功能"""
    print("🚀 AI个人助理 - 模型切换演示")
    print("=" * 50)

    config = get_config()

    # 测试消息
    test_message = "请用一句话介绍你自己。"

    # 测试DeepSeek
    print("\n🤖 测试 DeepSeek 模型:")
    print("-" * 30)
    try:
        config.model_provider = "deepseek"
        llm = LLMInterface(validate_keys=True)

        response = await llm.generate(test_message)
        print(f"🔹 模型: DeepSeek")
        print(f"🔹 响应: {response.content}")
        print(".2f")
    except Exception as e:
        print(f"❌ DeepSeek调用失败: {e}")

    # 测试Gemini（如果配额允许）
    print("\n🤖 测试 Gemini 模型:")
    print("-" * 30)
    try:
        config.model_provider = "gemini"
        llm = LLMInterface(validate_keys=True)

        response = await llm.generate(test_message)
        print(f"🔹 模型: Gemini")
        print(f"🔹 响应: {response.content}")
        print(".2f")
    except Exception as e:
        if "quota" in str(e).lower() or "429" in str(e):
            print("❌ Gemini配额已用完，请稍后再试或升级到付费版")
            print("💡 建议：使用DeepSeek作为主要模型")
        else:
            print(f"❌ Gemini调用失败: {e}")

    print("\n" + "=" * 50)
    print("✅ 演示完成！")
    print("\n💡 模型切换方法:")
    print("  1. 编辑 .env 文件中的 MODEL_PROVIDER")
    print("  2. 设置为 'gemini' 或 'deepseek'")
    print("  3. 重启程序即可切换模型")


if __name__ == "__main__":
    try:
        asyncio.run(demo_model_switching())
    except KeyboardInterrupt:
        print("\n👋 演示被用户中断")
    except Exception as e:
        print(f"\n❌ 演示过程中发生错误: {e}")
