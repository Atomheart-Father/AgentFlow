#!/usr/bin/env python3
"""
M3编排器测试脚本
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_m3_orchestrator():
    """测试M3编排器"""
    print("=== M3编排器测试 ===\n")

    try:
        # 导入M3模块
        from orchestrator import orchestrate_query, OrchestratorResult
        from schemas.plan import Plan, PlanStep, StepType

        # 测试查询
        test_query = "现在几点了？今天是星期几？"

        print(f"测试查询: {test_query}")
        print("开始编排...")

        # 执行编排
        result = await orchestrate_query(test_query, max_iterations=1)

        print("\n编排结果:")        print(f"状态: {result.status}")
        print(f"迭代次数: {result.iteration_count}")
        print(f"总时间: {result.total_time:.2f}s")

        if result.final_plan:
            print(f"计划步骤数: {len(result.final_plan.steps)}")
            for i, step in enumerate(result.final_plan.steps, 1):
                print(f"  步骤{i}: {step.type} - {step.tool or '无工具'}")

        if result.final_answer:
            print(f"\n最终答案: {result.final_answer}")

        if result.execution_state:
            print(f"执行产出: {len(result.execution_state.artifacts)} 个")
            for key, value in result.execution_state.artifacts.items():
                print(f"  {key}: {str(value)[:100]}...")

        if result.judge_history:
            print(f"判断历史: {len(result.judge_history)} 次")
            for i, judge in enumerate(result.judge_history, 1):
                print(f"  判断{i}: satisfied={judge.satisfied}, confidence={judge.confidence}")

        print("\n✅ M3编排器测试完成")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


async def test_agent_core_m3():
    """测试AgentCore的M3模式"""
    print("\n=== AgentCore M3模式测试 ===\n")

    try:
        from agent_core import create_agent_core_with_llm

        # 创建启用M3模式的Agent
        agent = create_agent_core_with_llm(use_m3=True)

        test_query = "帮我计算一下 (12+3*4)^2 的值"

        print(f"测试查询: {test_query}")
        print("使用M3模式处理...")

        result = await agent.process(test_query)

        print("\n处理结果:")        print(f"响应: {result['response']}")
        print(f"模式: {result['metadata'].get('mode', 'unknown')}")

        if 'iteration_count' in result['metadata']:
            print(f"迭代次数: {result['metadata']['iteration_count']}")
            print(f"计划步骤数: {result['metadata'].get('plan_steps', 0)}")
            print(f"执行产出数: {result['metadata'].get('execution_artifacts', 0)}")

        print("\n✅ AgentCore M3模式测试完成")

    except Exception as e:
        print(f"❌ AgentCore测试失败: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """主测试函数"""
    await test_m3_orchestrator()
    await test_agent_core_m3()


if __name__ == "__main__":
    asyncio.run(main())
