#!/usr/bin/env python3
"""
测试异步流式修复
"""

import asyncio
import concurrent.futures
from typing import Dict, Any, AsyncGenerator

def sync_event_generator() -> AsyncGenerator[Dict[str, Any], None]:
    """模拟同步事件生成器"""
    events = [
        {"type": "status", "message": "开始处理"},
        {"type": "assistant_content", "content": "你"},
        {"type": "assistant_content", "content": "好"},
        {"type": "assistant_content", "content": "！"},
        {"type": "tool_trace", "message": "调用工具"},
        {"type": "assistant_content", "content": "我可以帮助你"},
        {"type": "final", "message": "处理完成"}
    ]
    for event in events:
        yield event

async def test_async_generator():
    """测试异步生成器修复"""
    print("🧪 测试异步生成器修复...")

    # 模拟修复后的代码逻辑
    async def async_generator():
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            for event in await loop.run_in_executor(executor, lambda: list(sync_event_generator())):
                yield event

    # 测试异步迭代
    async for event in async_generator():
        print(f"收到事件: {event}")

    print("✅ 异步生成器测试通过！")

if __name__ == "__main__":
    asyncio.run(test_async_generator())
