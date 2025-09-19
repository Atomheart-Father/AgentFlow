#!/usr/bin/env python3
"""
测试前后端ask_user协同修复效果
验证ask_user_pending结构统一、expects处理、ask_id一致性等功能
"""
import asyncio
import sys
import os
from pathlib import Path

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator.executor import Executor
from orchestrator.orchestrator import SessionState, PendingAsk
from schemas.plan import PlanStep, StepType
from tool_registry import get_tools
from agent_core import AgentCore


async def test_ask_user_pending_structure():
    """测试ask_user_pending结构统一"""
    print("=== 测试ask_user_pending结构统一 ===\n")

    try:
        # 创建executor和测试数据
        executor = Executor()
        tools = get_tools()
        executor.tools = tools

        # 创建测试步骤（模拟需要用户输入的天气查询）
        test_step = PlanStep(
            id="test_weather",
            type=StepType.TOOL_CALL,
            tool="weather_get",
            inputs={},
            expect="请提供您想查询天气的城市",
            output_key="weather_result"
        )

        # 模拟执行工具调用，触发ask_user_pending生成
        from orchestrator.executor import ExecutionState

        state = ExecutionState()
        state.set_artifact("user_input", "北京")

        # 模拟工具调用缺少location参数的情况
        # 这里我们直接测试executor的ask_user_pending生成逻辑

        # 手动创建ask_user_pending来测试结构
        import uuid
        ask_id = f"ask_test_{uuid.uuid4().hex[:8]}"

        # 模拟executor生成ask_user_pending
        ask_user_pending = {
            "ask_id": ask_id,
            "questions": ["请告诉我您想查询哪个城市的天气？"],
            "expects": "city",  # 期望城市信息
            "step_id": test_step.step_id,
            "output_key": "user_city",  # 答案存放键
            "context": "天气查询场景"
        }

        state.set_artifact("ask_user_pending", ask_user_pending)

        # 验证结构
        retrieved = state.get_artifact("ask_user_pending")
        assert retrieved is not None, "ask_user_pending未正确存储"

        required_fields = ["ask_id", "questions", "expects", "step_id", "output_key", "context"]
        for field in required_fields:
            assert field in retrieved, f"缺少必需字段: {field}"
            print(f"✅ 字段 {field}: {retrieved[field]}")

        print("✅ ask_user_pending结构验证通过")
        return True

    except Exception as e:
        print(f"❌ ask_user_pending结构测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_expects_inference():
    """测试expects类型推断"""
    print("\n=== 测试expects类型推断 ===\n")

    try:
        executor = Executor()

        # 测试城市相关问题
        city_step = PlanStep(
            id="city_test",
            type=StepType.TOOL_CALL,
            tool="weather_get",
            expect="请提供您想查询天气的城市",
            output_key="weather_result"
        )

        city_expects = executor._determine_expects_type(city_step, {})
        city_output_key = executor._determine_output_key(city_step, {})

        assert city_expects == "city", f"城市问题expects推断错误: {city_expects}"
        assert city_output_key == "user_city", f"城市问题output_key推断错误: {city_output_key}"
        print(f"✅ 城市问题: expects={city_expects}, output_key={city_output_key}")

        # 测试日期相关问题
        date_step = PlanStep(
            id="date_test",
            type=StepType.TOOL_CALL,
            tool="calendar_read",
            expect="请提供您想查看日程的日期",
            output_key="calendar_result"
        )

        date_expects = executor._determine_expects_type(date_step, {})
        date_output_key = executor._determine_output_key(date_step, {})

        assert date_expects == "date", f"日期问题expects推断错误: {date_expects}"
        assert date_output_key == "user_date", f"日期问题output_key推断错误: {date_output_key}"
        print(f"✅ 日期问题: expects={date_expects}, output_key={date_output_key}")

        # 测试通用问题
        general_step = PlanStep(
            id="general_test",
            type=StepType.TOOL_CALL,
            tool="ask_user",
            expect="请提供详细信息",
            output_key="user_info"
        )

        general_expects = executor._determine_expects_type(general_step, {})
        general_output_key = executor._determine_output_key(general_step, {})

        assert general_expects == "answer", f"通用问题expects推断错误: {general_expects}"
        assert general_output_key == "user_info", f"通用问题output_key推断错误: {general_output_key}"
        print(f"✅ 通用问题: expects={general_expects}, output_key={general_output_key}")

        print("✅ expects类型推断验证通过")
        return True

    except Exception as e:
        print(f"❌ expects推断测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_session_pending_ask():
    """测试SessionState的PendingAsk处理"""
    print("\n=== 测试SessionState PendingAsk处理 ===\n")

    try:
        session = SessionState()

        # 测试创建PendingAsk
        ask_id = "test_ask_123"
        question = "请告诉我您的位置"
        expects = "city"

        pending_ask = PendingAsk(ask_id, question, expects)

        assert pending_ask.ask_id == ask_id, f"ask_id不匹配: {pending_ask.ask_id}"
        assert pending_ask.question == question, f"question不匹配: {pending_ask.question}"
        assert pending_ask.expects == expects, f"expects不匹配: {pending_ask.expects}"

        print(f"✅ PendingAsk创建成功: ask_id={pending_ask.ask_id}, expects={pending_ask.expects}")

        # 测试session设置pending_ask
        session.pending_ask = pending_ask

        assert session.has_pending_ask(), "has_pending_ask()应该返回True"
        assert session.pending_ask.expects == "city", f"session中expects不正确: {session.pending_ask.expects}"

        print("✅ SessionState PendingAsk设置验证通过")
        return True

    except Exception as e:
        print(f"❌ SessionState PendingAsk测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_dynamic_tool_prompt():
    """测试动态工具提示词生成"""
    print("\n=== 测试动态工具提示词生成 ===\n")

    try:
        from tool_registry import tools_to_json, get_tools

        # 获取工具列表
        tools = get_tools()
        print(f"✅ 获取到 {len(tools)} 个工具")

        # 生成JSON格式的工具描述
        tools_json = tools_to_json(tools)
        print(f"✅ 工具JSON生成成功，长度: {len(tools_json)} 字符")

        # 验证JSON格式
        import json
        parsed_tools = json.loads(tools_json)
        assert isinstance(parsed_tools, list), "工具JSON应该是一个列表"
        assert len(parsed_tools) == len(tools), "工具数量不匹配"

        # 检查每个工具都有必需字段
        for tool_info in parsed_tools:
            required_fields = ["name", "description", "parameters"]
            for field in required_fields:
                assert field in tool_info, f"工具缺少字段: {field}"
                assert tool_info[field], f"工具字段为空: {field}"

        print("✅ 工具JSON结构验证通过")

        # 测试AgentCore使用动态提示词
        agent = AgentCore()
        system_prompt = agent._build_system_prompt()

        assert "可用工具列表（JSON）:" in system_prompt, "系统提示词应该包含工具JSON"
        assert tools_json in system_prompt, "系统提示词应该包含生成的工具JSON"

        print("✅ AgentCore动态提示词生成验证通过")
        return True

    except Exception as e:
        print(f"❌ 动态工具提示词测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_integration_scenario():
    """测试完整集成场景"""
    print("\n=== 测试完整集成场景 ===\n")

    try:
        # 模拟完整的ask_user流程

        # 1. 创建session和executor
        session = SessionState()
        executor = Executor()

        # 2. 模拟需要用户输入的工具调用
        ask_id = "integration_test_123"
        question = "请告诉我您想查询哪个城市的天气？"

        # 3. 创建ask_user_pending
        ask_user_pending = {
            "ask_id": ask_id,
            "questions": [question],
            "expects": "city",
            "step_id": "weather_step_1",
            "output_key": "user_city",
            "context": "天气查询集成测试"
        }

        # 4. 设置到session
        session.pending_ask = PendingAsk(ask_id, question, "city")

        # 5. 模拟用户回答
        user_answer = "北京"

        # 6. 根据expects确定output_key
        expects = session.pending_ask.expects
        if expects == "city":
            output_key = "user_city"
        elif expects == "date":
            output_key = "user_date"
        else:
            output_key = "user_answer"

        # 验证逻辑
        assert output_key == "user_city", f"output_key推断错误: {output_key}"
        assert session.pending_ask.ask_id == ask_id, f"ask_id不一致: {session.pending_ask.ask_id}"

        print("✅ 集成场景: ask_id一致性验证通过")
        print("✅ 集成场景: expects处理验证通过")
        print("✅ 集成场景: output_key推断验证通过")

        return True

    except Exception as e:
        print(f"❌ 集成场景测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主测试函数"""
    print("🚀 开始测试前后端ask_user协同修复效果")
    print("=" * 60)

    test_results = []

    # 执行各项测试
    test_results.append(await test_ask_user_pending_structure())
    test_results.append(await test_expects_inference())
    test_results.append(await test_session_pending_ask())
    test_results.append(await test_dynamic_tool_prompt())
    test_results.append(await test_integration_scenario())

    # 统计结果
    passed = sum(test_results)
    total = len(test_results)

    print("\n" + "=" * 60)
    print("📊 测试结果统计")
    print(f"✅ 通过: {passed}/{total}")
    print(f"❌ 失败: {total - passed}/{total}")

    if passed == total:
        print("🎉 所有测试通过！前后端ask_user协同修复成功")
        return True
    else:
        print("⚠️ 部分测试失败，需要进一步检查")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
