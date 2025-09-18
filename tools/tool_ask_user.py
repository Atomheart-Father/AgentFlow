"""
询问用户工具 - 触发前端用户交互
"""

from typing import Dict, Any


class ToolAskUser:
    """询问用户工具"""

    def __init__(self):
        self.name = "ask_user"
        self.description = "向用户询问信息，触发前端交互界面。使用此工具来获取用户位置、具体名词等必要信息。"
        self.parameters = {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "要询问用户的问题，例如'您所在的城市是？'或'您说的他是指男主的父亲xxx还是指男主的宿敌xxx?'"
                },
                "context": {
                    "type": "string",
                    "description": "问题上下文，可选，用于说明为什么需要询问这个信息",
                    "default": ""
                }
            },
            "required": ["question"]
        }

    def run(self, question: str, context: str = "", **kwargs) -> Dict[str, Any]:
        """
        执行询问用户操作

        Args:
            question: 要询问的问题
            context: 上下文信息
            **kwargs: 其他参数

        Returns:
            包含问题的信息（实际的响应由前端处理）
        """
        # 这个工具不执行实际操作，只是返回问题信息
        # 前端会捕获这个工具调用并显示交互界面

        return {
            "action": "ask_user",
            "question": question,
            "context": context,
            "message": f"🤔 需要您的帮助：{question}",
            "requires_user_input": True
        }
