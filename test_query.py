#!/usr/bin/env python3
"""
测试查询脚本
执行查询："帮我查下明天天气，规划个行程，最后写到md文件里"
并将所有日志输出到文件
"""
import asyncio
import sys
import os
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_core import create_agent_core_with_llm
from config import get_config
from logger import setup_logging
import logging

# 设置日志输出到文件和控制台
def setup_test_logging(log_file):
    """设置测试日志"""
    # 创建logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # 清除现有handler
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # 文件handler
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(file_formatter)

    # 控制台handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)

    # 添加handler
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


async def run_test_query():
    """运行测试查询"""
    # 设置输出目录（按时间戳创建子目录）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(f"./output/{timestamp}")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 生成日志文件名
    log_file = output_dir / f"query_test_{timestamp}.log"

    print(f"开始测试查询，日志文件: {log_file}")

    # 设置日志
    logger = setup_test_logging(log_file)
    logger.info("=" * 50)
    logger.info("开始 AgentFlow 查询测试")
    logger.info("=" * 50)

    try:
        # 初始化配置
        config = get_config()
        logger.info(f"配置加载完成: M3={config.use_m3_orchestrator}, RAG={config.rag_enabled}")

        # 创建Agent实例
        logger.info("创建 Agent 实例...")
        agent = create_agent_core_with_llm(use_m3=True)
        logger.info("Agent 初始化完成")

        # 测试查询
        query = "帮我查下明天天气，规划个行程，最后写到md文件里"
        logger.info(f"执行查询: {query}")

        # 记录开始时间
        start_time = datetime.now()

        # 执行查询（流式处理）
        logger.info("开始流式处理...")
        full_response = ""
        event_count = 0

        ask_user_encountered = False
        user_answer = "北京"  # 预设的用户回答

        async for event in agent.process_stream(query):
            event_count += 1
            event_type = event.get("type", "unknown")
            logger.info(f"[事件 {event_count}] 类型: {event_type}")

            if event_type == "content":
                content = event.get("content", "")
                full_response += content
                logger.debug(f"内容片段: {content[:100]}...")
            elif event_type == "status":
                status_msg = event.get("message", "")
                logger.info(f"状态: {status_msg}")
            elif event_type == "tool_result":
                tool_name = event.get("tool_name", "")
                result = str(event.get("result", ""))[:200]
                logger.info(f"工具结果: {tool_name} -> {result}...")
            elif event_type == "final":
                final_response = event.get("response", "")
                metadata = event.get("metadata", {})
                logger.info(f"最终结果: {final_response[:200]}...")
                logger.info(f"元数据: {metadata}")
            elif event_type == "error":
                error_msg = event.get("error", "")
                logger.error(f"错误: {error_msg}")
            elif event_type == "ask_user":
                question = event.get("question", "")
                logger.info(f"需要用户输入: {question}")
                logger.info(f"模拟用户回答: {user_answer}")
                ask_user_encountered = True

                # 模拟用户回答后继续执行
                # 在真实场景中，这里会等待用户输入，然后重新调用
                logger.info("模拟用户回答后重新执行查询...")

                # 创建一个新的查询包含用户回答
                enhanced_query = f"{query}\n\n用户回答: {user_answer}"
                logger.info(f"增强查询: {enhanced_query}")

                # 重新执行查询
                logger.info("开始续跑执行...")
                async for followup_event in agent.process_stream(enhanced_query):
                    event_count += 1
                    followup_event_type = followup_event.get("type", "unknown")
                    logger.info(f"[续跑事件 {event_count}] 类型: {followup_event_type}")

                    if followup_event_type == "content":
                        content = followup_event.get("content", "")
                        full_response += content
                        logger.debug(f"续跑内容片段: {content[:100]}...")
                    elif followup_event_type == "status":
                        status_msg = followup_event.get("message", "")
                        logger.info(f"续跑状态: {status_msg}")
                    elif followup_event_type == "tool_result":
                        tool_name = followup_event.get("tool_name", "")
                        result = str(followup_event.get("result", ""))[:200]
                        logger.info(f"续跑工具结果: {tool_name} -> {result}...")
                    elif followup_event_type == "final":
                        final_response = followup_event.get("response", "")
                        metadata = followup_event.get("metadata", {})
                        logger.info(f"续跑最终结果: {final_response[:200]}...")
                        logger.info(f"续跑元数据: {metadata}")
                        break  # 续跑完成
                    elif followup_event_type == "error":
                        error_msg = followup_event.get("error", "")
                        logger.error(f"续跑错误: {error_msg}")
                        break
                    elif followup_event_type == "ask_user":
                        # 续跑中再次遇到ask_user，记录但不处理
                        question = followup_event.get("question", "")
                        logger.info(f"续跑中再次遇到ask_user: {question}")
                        logger.info("续跑结束，避免无限循环")
                        break
                    else:
                        logger.debug(f"续跑其他事件: {followup_event}")

                break  # 主循环结束，因为已经处理了续跑
            else:
                logger.debug(f"其他事件: {event}")

        # 记录结束时间
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info("=" * 50)
        logger.info("查询测试完成")
        logger.info(f"总耗时: {duration:.2f}秒")
        logger.info(f"处理事件数: {event_count}")
        logger.info(f"最终响应长度: {len(full_response)} 字符")
        logger.info("=" * 50)

        # 保存最终结果到单独的文件
        result_file = output_dir / f"query_result_{timestamp}.txt"
        with open(result_file, 'w', encoding='utf-8') as f:
            f.write("查询测试结果\n")
            f.write("=" * 30 + "\n")
            f.write(f"查询: {query}\n")
            f.write(f"开始时间: {start_time}\n")
            f.write(f"结束时间: {end_time}\n")
            f.write(f"总耗时: {duration:.2f}秒\n")
            f.write(f"事件数: {event_count}\n")
            f.write("\n最终响应:\n")
            f.write("-" * 20 + "\n")
            f.write(full_response)
            f.write("\n" + "=" * 50 + "\n")

        logger.info(f"结果已保存到: {result_file}")

        print("\n" + "=" * 50)
        print("测试完成！")
        print(f"日志文件: {log_file}")
        print(f"结果文件: {result_file}")
        print("=" * 50)

    except Exception as e:
        logger.error(f"测试过程中发生错误: {e}", exc_info=True)
        print(f"❌ 测试失败: {e}")
        return False

    return True


if __name__ == "__main__":
    success = asyncio.run(run_test_query())
    sys.exit(0 if success else 1)
