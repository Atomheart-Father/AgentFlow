#!/usr/bin/env python3
"""
API密钥测试脚本
验证Gemini和DeepSeek API密钥是否正确设置
"""
import sys
from config import get_config
from logger import setup_logging, get_logger

# 初始化日志
setup_logging("INFO")
logger = get_logger()


def test_config():
    """测试配置"""
    print("🔧 测试配置...")
    config = get_config()

    print(f"  当前提供商: {config.model_provider}")
    print(f"  Gemini Key: {'✓ 已设置' if config.gemini_api_key else '✗ 未设置'}")
    print(f"  DeepSeek Key: {'✓ 已设置' if config.deepseek_api_key else '✗ 未设置'}")
    print(f"  可用提供商: {config.get_available_providers()}")

    return config


def test_llm_interface(config):
    """测试LLM接口"""
    print("\n🤖 测试LLM接口...")

    try:
        from llm_interface import LLMInterface
        llm = LLMInterface(validate_keys=False)
        print("  LLM接口创建: ✓ 成功")
        print(f"  提供者初始化: {'✓ 已初始化' if llm.provider else '○ 未初始化'}")

        # 测试初始化提供者
        if config.get_available_providers():
            try:
                llm.initialize_provider()
                print("  提供者初始化: ✓ 成功")
                if hasattr(llm.provider, 'model'):
                    print(f"  当前模型: {llm.provider.model}")
                elif hasattr(llm.provider, 'model_name'):
                    print(f"  当前模型: {llm.provider.model_name}")
                else:
                    print("  当前模型: unknown")
            except Exception as e:
                print(f"  提供者初始化: ✗ 失败 - {e}")
        else:
            print("  提供者初始化: ⚠ 跳过（无可用API密钥）")

        return llm

    except Exception as e:
        print(f"  LLM接口创建: ✗ 失败 - {e}")
        return None


def test_agent_core(llm):
    """测试Agent核心"""
    print("\n🧠 测试Agent核心...")

    try:
        from agent_core import AgentCore
        agent = AgentCore(llm_interface=llm if llm and llm.provider else None)
        print("  Agent核心创建: ✓ 成功")
        print(f"  LLM集成: {'✓ 已集成' if agent.llm and agent.llm.provider else '○ 未集成'}")

        return agent

    except Exception as e:
        print(f"  Agent核心创建: ✗ 失败 - {e}")
        return None


def main():
    """主函数"""
    print("🚀 API密钥测试")
    print("=" * 50)

    # 测试配置
    config = test_config()

    # 测试LLM接口
    llm = test_llm_interface(config)

    # 测试Agent核心
    agent = test_agent_core(llm)

    # 总结
    print("\n📊 测试总结")
    print("-" * 30)

    success_count = 0
    total_tests = 3

    if config.gemini_api_key or config.deepseek_api_key:
        success_count += 1
        print("✓ 配置测试: 通过")
    else:
        print("✗ 配置测试: 需要设置API密钥")

    if llm:
        success_count += 1
        print("✓ LLM接口测试: 通过")
    else:
        print("✗ LLM接口测试: 失败")

    if agent:
        success_count += 1
        print("✓ Agent核心测试: 通过")
    else:
        print("✗ Agent核心测试: 失败")

    print(f"\n🎯 总体状态: {success_count}/{total_tests} 测试通过")

    if success_count == total_tests:
        print("🎉 所有测试通过！系统准备就绪。")
    else:
        print("⚠️  请检查配置和依赖。")

    print("\n💡 使用提示:")
    print("  1. 编辑 .env 文件设置真实的API密钥")
    print("  2. 运行 python main.py --validate-keys 验证密钥")
    print("  3. 运行 python main.py 启动系统")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 测试被用户中断")
    except Exception as e:
        print(f"\n\n❌ 测试过程中发生错误: {e}")
        sys.exit(1)
