"""
询问用户工具 - 触发前端用户交互
"""

from typing import Dict, Any


class ToolAskUser:
    """询问用户工具"""

    def __init__(self):
        self.name = "ask_user"
        self.description = "向用户询问信息，触发前端交互界面。支持城市、日期、通用答案等类型，使用此工具来获取缺失的必要信息。"
        self.parameters = {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要询问用户的问题列表（UI只取第一个）"
                },
                "expects": {
                    "type": "string",
                    "enum": ["city", "date", "answer"],
                    "description": "期望的答案类型，影响前端渲染方式",
                    "default": "answer"
                },
                "output_key": {
                    "type": "string",
                    "description": "答案存放的键名，默认为user_city/user_date/user_answer",
                    "default": ""
                },
                "context": {
                    "type": "string",
                    "description": "问题上下文，可选，用于说明为什么需要询问这个信息",
                    "default": ""
                }
            },
            "required": ["questions"]
        }

    def run(self, questions: list = None, expects: str = "answer", output_key: str = "", context: str = "", **kwargs) -> Dict[str, Any]:
        """
        执行询问用户操作

        Args:
            questions: 要询问的问题列表（兼容旧版question参数）
            expects: 期望的答案类型 (city/date/answer)
            output_key: 答案存放的键名
            context: 上下文信息
            **kwargs: 其他参数（包含state等）

        Returns:
            ask_user_pending结构（由executor统一处理）
        """
        import uuid
        import time

        # 兼容旧版API（question参数）
        if not questions and "question" in kwargs:
            questions = [kwargs["question"]]

        # 确保questions是列表
        if isinstance(questions, str):
            questions = [questions]

        # 确定output_key
        if not output_key:
            if expects == "city":
                output_key = "user_city"
            elif expects == "date":
                output_key = "user_date"
            else:
                output_key = "user_answer"

        # 生成ask_id
        ask_id = f"ask_{int(time.time())}_{uuid.uuid4().hex[:8]}"

        # 构建完整的ask_user_pending结构
        ask_user_pending = {
            "ask_id": ask_id,
            "questions": questions,
            "expects": expects,
            "step_id": kwargs.get("step_id", ""),
            "output_key": output_key,
            "context": context
        }

        # 获取state并设置ask_user_pending
        state = kwargs.get("state")
        if state:
            state.set_artifact("ask_user_pending", ask_user_pending)

        return {
            "action": "ask_user",
            "status": "ask_user_pending",
            "ask_id": ask_id,
            "questions": questions,
            "expects": expects,
            "output_key": output_key,
            "message": f"🤔 需要您的帮助：{questions[0] if questions else '请提供信息'}",
            "requires_user_input": True
        }
