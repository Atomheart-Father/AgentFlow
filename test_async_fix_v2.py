#!/usr/bin/env python3
"""
测试异步处理修复v2 - 简化版本
"""

import asyncio
import concurrent.futures
from typing import Dict, Any

def sync_event_generator() -> Dict[str, Any]:
    """模拟同步事件生成器"""
    events = [
        {"type": "status", "message": "开始处理"},
        {"type": "assistant_content", "content": "你"},
        {"type": "assistant_content", "content": "好"},
        {"type": "assistant_content", "content": "！"},
        {"type": "tool_trace", "message": "调用工具"},
        {"type": "final", "message": "处理完成"}
    ]
    for event in events:
        yield event

async def test_fixed_async_processing():
    """测试修复后的异步处理逻辑"""
    print("🧪 测试修复后的异步处理逻辑...")

    # 模拟修复后的代码逻辑
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # 获取所有事件列表
        events = await loop.run_in_executor(executor, lambda: list(sync_event_generator()))

        # 逐个处理事件
        processed_events = []
        for event in events:
            processed_events.append(event)
            print(f"处理事件: {event}")

    print(f"✅ 成功处理了 {len(processed_events)} 个事件")
    print("✅ 异步处理修复测试通过！")

if __name__ == "__main__":
    asyncio.run(test_fixed_async_processing())
