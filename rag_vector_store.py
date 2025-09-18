"""
RAG向量存储模块
基于ChromaDB的简单向量存储实现
"""

import os
from typing import List, Dict, Any, Optional
from pathlib import Path


class RAGVectorStore:
    """RAG向量存储"""

    def __init__(self, persist_directory: str = "./data/chroma"):
        """
        初始化RAG向量存储

        Args:
            persist_directory: 数据持久化目录
        """
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.is_initialized = False
        self.collection_name = "agent_documents"

    def initialize(self):
        """初始化向量存储"""
        try:
            import chromadb
            from chromadb.config import Settings

            # 初始化Chroma客户端
            self.client = chromadb.PersistentClient(
                path=str(self.persist_directory),
                settings=Settings(anonymized_telemetry=False)
            )

            # 获取或创建集合
            try:
                self.collection = self.client.get_collection(name=self.collection_name)
            except ValueError:
                self.collection = self.client.create_collection(name=self.collection_name)

            self.is_initialized = True
            print(f"RAG向量存储初始化成功，数据目录: {self.persist_directory}")

        except ImportError:
            print("警告: 未安装ChromaDB，RAG功能将不可用")
            print("安装命令: pip install chromadb")
            self.is_initialized = False

    def add_texts(self, texts: List[str], metadatas: Optional[List[Dict[str, Any]]] = None) -> List[str]:
        """
        添加文本到向量存储

        Args:
            texts: 文本列表
            metadatas: 元数据列表

        Returns:
            添加的文档ID列表
        """
        if not self.is_initialized:
            print("RAG存储未初始化")
            return []

        if not texts:
            return []

        try:
            # 生成文档ID
            import uuid
            ids = [str(uuid.uuid4()) for _ in texts]

            # 准备元数据
            if metadatas is None:
                metadatas = [{}] * len(texts)

            # 确保所有文档都有source字段
            for metadata in metadatas:
                if "source" not in metadata:
                    metadata["source"] = "unknown"

            # 添加到集合
            self.collection.add(
                documents=texts,
                metadatas=metadatas,
                ids=ids
            )

            print(f"成功添加 {len(texts)} 个文档到RAG存储")
            return ids

        except Exception as e:
            print(f"添加文档到RAG存储失败: {e}")
            return []

    def query(self, query_text: str, n_results: int = 5) -> Dict[str, Any]:
        """
        查询相关文档

        Args:
            query_text: 查询文本
            n_results: 返回结果数量

        Returns:
            查询结果字典
        """
        if not self.is_initialized:
            print("RAG存储未初始化")
            return {"documents": [], "metadatas": [], "distances": []}

        try:
            # 执行查询
            results = self.collection.query(
                query_texts=[query_text],
                n_results=n_results
            )

            # 格式化结果
            formatted_results = {
                "documents": results.get("documents", [[]])[0],
                "metadatas": results.get("metadatas", [[]])[0],
                "distances": results.get("distances", [[]])[0] if "distances" in results else []
            }

            print(f"RAG查询完成，返回 {len(formatted_results['documents'])} 个结果")
            return formatted_results

        except Exception as e:
            print(f"RAG查询失败: {e}")
            return {"documents": [], "metadatas": [], "distances": []}

    def get_stats(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        if not self.is_initialized:
            return {"status": "未初始化", "document_count": 0}

        try:
            count = self.collection.count()
            return {
                "status": "正常",
                "document_count": count,
                "collection_name": self.collection_name,
                "persist_directory": str(self.persist_directory)
            }
        except Exception as e:
            return {"status": f"错误: {e}", "document_count": 0}

    def clear_all(self):
        """清空所有文档"""
        if not self.is_initialized:
            print("RAG存储未初始化")
            return

        try:
            # 删除并重新创建集合
            self.client.delete_collection(name=self.collection_name)
            self.collection = self.client.create_collection(name=self.collection_name)
            print("RAG存储已清空")
        except Exception as e:
            print(f"清空RAG存储失败: {e}")


# 全局实例
rag_store = RAGVectorStore()


def get_rag_store() -> RAGVectorStore:
    """获取RAG存储实例"""
    return rag_store


def initialize_rag():
    """初始化RAG系统"""
    rag_store.initialize()


if __name__ == "__main__":
    # 测试代码
    print("=== RAG向量存储测试 ===")

    # 初始化
    initialize_rag()

    # 获取统计信息
    stats = rag_store.get_stats()
    print(f"存储状态: {stats}")

    if rag_store.is_initialized:
        # 添加测试文档
        test_texts = [
            "人工智能是计算机科学的一个分支，致力于创建智能机器。",
            "机器学习是人工智能的一个子领域，专注于让计算机从数据中学习。",
            "深度学习使用神经网络来进行模式识别和学习。",
            "自然语言处理让计算机能够理解和生成人类语言。"
        ]

        test_metadatas = [
            {"source": "ai_intro.txt", "topic": "AI基础"},
            {"source": "ml_guide.txt", "topic": "机器学习"},
            {"source": "dl_tutorial.txt", "topic": "深度学习"},
            {"source": "nlp_overview.txt", "topic": "自然语言处理"}
        ]

        # 添加文档
        ids = rag_store.add_texts(test_texts, test_metadatas)
        print(f"添加了 {len(ids)} 个文档")

        # 测试查询
        query_result = rag_store.query("什么是人工智能？", n_results=2)
        print(f"查询结果: {len(query_result['documents'])} 个文档")

        for i, doc in enumerate(query_result['documents']):
            print(f"文档 {i+1}: {doc[:100]}...")

        # 显示最终统计
        final_stats = rag_store.get_stats()
        print(f"最终状态: {final_stats}")
    else:
        print("RAG存储初始化失败，请安装ChromaDB: pip install chromadb")
