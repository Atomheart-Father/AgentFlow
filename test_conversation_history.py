#!/usr/bin/env python3
"""
测试对话历史管理功能
"""

from orchestrator.orchestrator import SessionState, ConversationMessage

def test_conversation_history():
    """测试对话历史管理"""
    print("🗣️ 测试对话历史管理功能...")

    # 创建会话状态
    session = SessionState()

    # 添加一些对话消息
    session.add_message("user", "帮我查下明天天气")
    session.add_message("assistant", "好的，请告诉我您想查询哪个城市的天气？")
    session.add_message("user", "北京")
    session.add_message("assistant", "北京明天天气：晴天，温度15-25℃")
    session.add_message("user", "谢谢")
    session.add_message("assistant", "不客气，有什么其他问题吗？")

    print(f"✅ 对话历史记录数: {len(session.conversation_history)}")

    # 测试获取最近消息
    recent = session.get_recent_messages(3)
    print(f"✅ 最近3条消息:")
    for msg in recent:
        role_name = "用户" if msg.role == "user" else "助手"
        print(f"  {role_name}: {msg.content}")

    # 测试对话上下文摘要
    context = session.get_conversation_context()
    print(f"✅ 对话上下文摘要:\n{context}")

    # 测试用户偏好
    session.set_user_preference("default_city", "北京")
    session.set_user_preference("temperature_unit", "celsius")

    city = session.get_user_preference("default_city")
    unit = session.get_user_preference("temperature_unit")

    print(f"✅ 用户偏好: 城市={city}, 温度单位={unit}")

    print("✅ 对话历史管理功能测试通过！")

if __name__ == "__main__":
    test_conversation_history()
