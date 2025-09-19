"""
RAG 搜索工具
基于本地 Chroma 向量库实现文档搜索
"""
import time
from typing import List, Dict, Any, Optional
from pathlib import Path

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

from schemas.tool_result import StandardToolResult, ToolError, ErrorCode, create_tool_meta, create_tool_error


class ToolRAGSearch:
    """RAG搜索工具"""

    def __init__(self):
        self.name = "rag_search"
        self.description = "在本地文档库中搜索相关内容"
        self.parameters = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询"
                },
                "top_k": {
                    "type": "integer",
                    "default": 3,
                    "minimum": 1,
                    "maximum": 10,
                    "description": "返回结果的最大数量"
                }
            },
            "required": ["query"]
        }

        # Chroma 配置
        self.persist_dir = Path("./.agentflow/chroma")
        self.collection_name = "agent_documents"
        self.client = None
        self.collection = None

        # 初始化
        self._initialize_chroma()

    def _initialize_chroma(self):
        """初始化 Chroma 客户端"""
        if not CHROMA_AVAILABLE:
            print("警告: ChromaDB 未安装，RAG 搜索功能将不可用")
            return

        try:
            self.client = chromadb.PersistentClient(
                path=str(self.persist_dir),
                settings=Settings(anonymized_telemetry=False)
            )

            # 获取集合
            try:
                self.collection = self.client.get_collection(name=self.collection_name)
                print(f"✅ 找到 RAG 集合: {self.collection_name}")
            except Exception as e:
                print(f"警告: RAG 集合不存在，请先运行文档摄入: {e}")
                self.collection = None

        except Exception as e:
            print(f"Chroma 初始化失败: {e}")
            self.collection = None

    def _is_available(self) -> bool:
        """检查 RAG 是否可用"""
        return self.collection is not None

    def _format_result(self, query: str, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """格式化搜索结果"""
        formatted_results = []

        if not results or not results.get('documents'):
            return formatted_results

        documents = results['documents'][0] if isinstance(results['documents'], list) and results['documents'] else results['documents']
        metadatas = results['metadatas'][0] if isinstance(results['metadatas'], list) and results['metadatas'] else results['metadatas']
        distances = results['distances'][0] if isinstance(results['distances'], list) and results['distances'] else results['distances']

        for i, (doc, metadata, distance) in enumerate(zip(documents, metadatas, distances or [0] * len(documents))):
            # 计算相似度分数（距离越小分数越高）
            score = max(0, 1 - distance) if distance is not None else 0.5

            # 创建片段（限制长度）
            snippet = doc[:500] + "..." if len(doc) > 500 else doc

            formatted_results.append({
                "path": metadata.get("source", "unknown"),
                "chunk_id": metadata.get("id", f"chunk_{i}"),
                "score": round(score, 3),
                "snippet": snippet,
                "file_path": metadata.get("file_path", ""),
                "chunk_index": metadata.get("chunk_index", 0),
                "total_chunks": metadata.get("total_chunks", 1),
                "ingested_at": metadata.get("ingested_at", 0)
            })

        return formatted_results

    def run(self, query: str, top_k: int = 3) -> StandardToolResult:
        """
        执行 RAG 搜索

        Args:
            query: 搜索查询
            top_k: 返回结果的最大数量

        Returns:
            标准化的工具结果
        """
        start_time = time.time()

        try:
            # 检查可用性
            if not self._is_available():
                error = create_tool_error(
                    ErrorCode.INTERNAL,
                    "RAG 搜索不可用：请先运行文档摄入 (python -m rag.ingest --src ./notes)",
                    retryable=False
                )
                meta = create_tool_meta(self.name, 0, {"query": query, "top_k": top_k})
                return StandardToolResult.failure(error, meta)

            # 执行搜索
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k,
                include=['documents', 'metadatas', 'distances']
            )

            # 格式化结果
            formatted_results = self._format_result(query, results)

            # 创建成功结果
            latency_ms = int((time.time() - start_time) * 1000)
            meta = create_tool_meta(self.name, latency_ms, {
                "query": query,
                "top_k": top_k,
                "results_count": len(formatted_results)
            })

            result_data = {
                "query": query,
                "results": formatted_results,
                "total_found": len(formatted_results)
            }

            return StandardToolResult.success(result_data, meta)

        except Exception as e:
            # 错误处理
            latency_ms = int((time.time() - start_time) * 1000)
            error = create_tool_error(
                ErrorCode.INTERNAL,
                f"RAG 搜索失败: {str(e)}",
                retryable=True
            )
            meta = create_tool_meta(self.name, latency_ms, {
                "query": query,
                "top_k": top_k
            })
            return StandardToolResult.failure(error, meta)

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        便捷搜索方法

        Args:
            query: 搜索查询
            top_k: 返回结果的最大数量

        Returns:
            搜索结果列表
        """
        result = self.run(query, top_k)
        if result.ok and result.data:
            return result.data.get("results", [])
        return []
