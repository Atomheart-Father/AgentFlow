"""
RAG存储接口定义
为历史对话记录预留的RAG数据库接口
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime


class ConversationData:
    """对话数据结构"""

    def __init__(self, **kwargs):
        self.id: str = kwargs.get("id", "")
        self.title: str = kwargs.get("title", "")
        self.content: str = kwargs.get("content", "")  # 格式化的对话文本
        self.metadata: Dict[str, Any] = kwargs.get("metadata", {})
        self.raw_history: List[tuple] = kwargs.get("raw_history", [])  # [(user_msg, ai_msg), ...]
        self.raw_metadata: List[Dict] = kwargs.get("raw_metadata", [])


class RAGStoreInterface(ABC):
    """RAG存储接口抽象基类"""

    @abstractmethod
    async def save_conversation(self, conversation: Dict[str, Any]) -> bool:
        """
        保存对话到RAG数据库

        Args:
            conversation: 对话数据，包含：
                - id: 对话ID
                - title: 对话标题
                - content: 格式化的对话文本
                - metadata: 元数据（消息数、token数、模式等）
                - raw_history: 原始聊天历史
                - raw_metadata: 原始元数据

        Returns:
            bool: 保存是否成功
        """
        pass

    @abstractmethod
    async def load_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        从RAG数据库加载对话

        Args:
            conversation_id: 对话ID

        Returns:
            Optional[Dict]: 对话数据，如果不存在返回None
        """
        pass

    @abstractmethod
    async def delete_conversation(self, conversation_id: str) -> bool:
        """
        从RAG数据库删除对话

        Args:
            conversation_id: 对话ID

        Returns:
            bool: 删除是否成功
        """
        pass

    @abstractmethod
    async def list_conversations(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        获取对话列表

        Args:
            limit: 返回的最大数量
            offset: 偏移量

        Returns:
            List[Dict]: 对话列表，每个包含id, title, created_at, updated_at, message_count等
        """
        pass

    @abstractmethod
    async def search_conversations(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        搜索相关对话

        Args:
            query: 搜索查询
            limit: 返回的最大数量

        Returns:
            List[Dict]: 搜索结果，每个包含id, title, content_snippet, score等
        """
        pass

    @abstractmethod
    async def update_conversation_metadata(self, conversation_id: str, metadata: Dict[str, Any]) -> bool:
        """
        更新对话元数据

        Args:
            conversation_id: 对话ID
            metadata: 新的元数据

        Returns:
            bool: 更新是否成功
        """
        pass

    @abstractmethod
    async def get_conversation_stats(self) -> Dict[str, Any]:
        """
        获取对话统计信息

        Returns:
            Dict: 包含总对话数、总消息数、存储大小等统计信息
        """
        pass


# 预留的RAG存储实现类名
class ChromaRAGStore(RAGStoreInterface):
    """基于Chroma的RAG存储实现（待实现）"""
    pass


class PineconeRAGStore(RAGStoreInterface):
    """基于Pinecone的RAG存储实现（待实现）"""
    pass


class WeaviateRAGStore(RAGStoreInterface):
    """基于Weaviate的RAG存储实现（待实现）"""
    pass


def create_rag_store(store_type: str = "chroma", **kwargs) -> RAGStoreInterface:
    """
    创建RAG存储实例

    Args:
        store_type: 存储类型 ("chroma", "pinecone", "weaviate")
        **kwargs: 初始化参数

    Returns:
        RAGStoreInterface: RAG存储实例

    Raises:
        NotImplementedError: 当指定的存储类型尚未实现时
    """
    if store_type == "chroma":
        raise NotImplementedError("Chroma RAG存储尚未实现")
    elif store_type == "pinecone":
        raise NotImplementedError("Pinecone RAG存储尚未实现")
    elif store_type == "weaviate":
        raise NotImplementedError("Weaviate RAG存储尚未实现")
    else:
        raise ValueError(f"不支持的RAG存储类型: {store_type}")


# 使用示例（当RAG数据库接入时）：
"""
# 在ui_gradio.py中初始化RAG存储
from rag_store_interface import create_rag_store

# 在ChatUI.__init__中
self.rag_store = create_rag_store("chroma", persist_directory="./rag_data")

# 或者暂时设为None，使用内存缓存
self.rag_store = None
"""
