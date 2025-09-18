"""
邮件读取工具 - 模拟本地邮箱数据
"""

import json
from typing import Dict, Any, List
from pathlib import Path
from datetime import datetime, timedelta


class ToolEmail:
    """邮件读取工具"""

    def __init__(self):
        self.name = "email.list"
        self.description = "从本地邮箱数据中读取邮件，支持按发件人、主题等条件过滤"
        self.parameters = {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "返回的最大邮件数量，默认10",
                    "default": 10
                },
                "sender": {
                    "type": "string",
                    "description": "按发件人邮箱过滤"
                },
                "subject_contains": {
                    "type": "string",
                    "description": "按主题包含的关键词过滤"
                },
                "unread_only": {
                    "type": "boolean",
                    "description": "只返回未读邮件",
                    "default": False
                }
            },
            "required": []
        }

        # 邮件数据文件路径
        self.data_file = Path(__file__).parent.parent / "data" / "mailbox.json"
        self._ensure_data_file()

    def _ensure_data_file(self):
        """确保数据文件存在"""
        self.data_file.parent.mkdir(parents=True, exist_ok=True)

        if not self.data_file.exists():
            # 创建示例邮件数据
            now = datetime.now()
            sample_emails = [
                {
                    "id": 1,
                    "from": "boss@company.com",
                    "to": "me@company.com",
                    "subject": "Q1项目进度报告",
                    "snippet": "请查看附件中的项目进度报告...",
                    "received": (now - timedelta(hours=2)).isoformat(),
                    "read": False,
                    "has_attachments": True
                },
                {
                    "id": 2,
                    "from": "hr@company.com",
                    "to": "me@company.com",
                    "subject": "薪资调整通知",
                    "snippet": "根据公司政策和您的表现...",
                    "received": (now - timedelta(days=1)).isoformat(),
                    "read": False,
                    "has_attachments": False
                },
                {
                    "id": 3,
                    "from": "client@partner.com",
                    "to": "me@company.com",
                    "subject": "合作项目需求确认",
                    "snippet": "关于下个月的合作项目，我们需要确认以下需求...",
                    "received": (now - timedelta(days=2)).isoformat(),
                    "read": True,
                    "has_attachments": False
                },
                {
                    "id": 4,
                    "from": "newsletter@tech.com",
                    "to": "me@company.com",
                    "subject": "AI技术周刊 - 第45期",
                    "snippet": "本周AI技术热点：大语言模型进展...",
                    "received": (now - timedelta(days=3)).isoformat(),
                    "read": True,
                    "has_attachments": False
                },
                {
                    "id": 5,
                    "from": "system@company.com",
                    "to": "me@company.com",
                    "subject": "系统维护通知",
                    "snippet": "本周末将进行系统维护...",
                    "received": (now - timedelta(days=5)).isoformat(),
                    "read": True,
                    "has_attachments": False
                }
            ]

            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(sample_emails, f, indent=2, ensure_ascii=False)

    def _load_email_data(self) -> List[Dict[str, Any]]:
        """加载邮件数据"""
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            raise ValueError(f"加载邮件数据失败: {e}")

    def run(self, limit: int = 10, sender: str = None, subject_contains: str = None,
            unread_only: bool = False, **kwargs) -> Dict[str, Any]:
        """
        查询邮件列表

        Args:
            limit: 最大返回数量
            sender: 发件人邮箱过滤
            subject_contains: 主题关键词过滤
            unread_only: 只返回未读邮件
            **kwargs: 其他参数

        Returns:
            邮件列表
        """
        try:
            # 加载数据
            all_emails = self._load_email_data()

            # 应用过滤条件
            filtered_emails = []
            for email in all_emails:
                # 未读过滤
                if unread_only and email.get("read", True):
                    continue

                # 发件人过滤
                if sender and sender.lower() not in email["from"].lower():
                    continue

                # 主题关键词过滤
                if subject_contains and subject_contains.lower() not in email["subject"].lower():
                    continue

                filtered_emails.append(email)

            # 按接收时间倒序排序（最新的在前）
            filtered_emails.sort(key=lambda x: x["received"], reverse=True)

            # 限制数量
            filtered_emails = filtered_emails[:limit]

            result = {
                "query": {
                    "limit": limit,
                    "sender": sender,
                    "subject_contains": subject_contains,
                    "unread_only": unread_only
                },
                "total_found": len(filtered_emails),
                "emails": filtered_emails
            }

            return result

        except Exception as e:
            raise ValueError(f"邮件查询失败: {e}")
