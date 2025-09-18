#!/usr/bin/env python3
"""
测试PROCESS步骤类型的修复
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator.executor import Executor, ExecutionState
from schemas.plan import Plan, PlanStep, StepType
from llm_interface import create_llm_interface_with_keys
import json

async def test_process_step():
    """测试PROCESS步骤类型"""
    print("=== 测试PROCESS步骤类型 ===\n")

    try:
        # 创建执行器（不需要传入llm参数）
        executor = Executor()

        # 创建执行状态
        state = ExecutionState()

        # 设置测试数据
        test_weather_data = {
            "weather": "多云",
            "temperature": "18°C",
            "humidity": "65%",
            "wind": "西北风3级",
            "rain_probability": "20%"
        }
        state.set_artifact("weather_data", test_weather_data)

        # 创建PROCESS类型的步骤
        process_step = PlanStep(
            id="test_process",
            type=StepType.PROCESS,
            inputs={"weather_data": "weather_data"},
            depends_on=["weather_data"],
            expect="基于天气数据生成3条通勤建议",
            output_key="commute_advice"
        )

        print("1. 执行PROCESS步骤...")
        await executor._execute_process(process_step, {"weather_data": test_weather_data}, state)

        print("2. 获取结果...")
        result = state.get_artifact("commute_advice")
        print(f"结果: {result}")

        print("\n✅ PROCESS步骤测试成功")

    except Exception as e:
        print(f"❌ PROCESS步骤测试失败: {e}")
        import traceback
        traceback.print_exc()

async def test_plan_with_process():
    """测试包含PROCESS步骤的完整计划"""
    print("\n=== 测试包含PROCESS步骤的计划 ===\n")

    try:
        from orchestrator.orchestrator import get_orchestrator

        # 创建编排器
        orchestrator = get_orchestrator()

        # 测试查询
        query = "今天天气怎么样？给我一些通勤建议"

        print(f"查询: {query}")
        result = await orchestrator.orchestrate(query)

        print(f"状态: {result.status}")
        print(f"执行步骤数: {len(result.final_plan.steps) if result.final_plan else 0}")
        print(f"工具调用数: {len(result.execution_state.artifacts) if result.execution_state else 0}")

        print("\n✅ 完整计划测试成功")

    except Exception as e:
        print(f"❌ 完整计划测试失败: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """主测试函数"""
    await test_process_step()
    await test_plan_with_process()

if __name__ == "__main__":
    asyncio.run(main())
