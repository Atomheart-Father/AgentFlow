"""
RAG 文档摄入模块
递归读取 ./notes/ 下的 .md/.txt/.pdf 文件，切块并存入本地 Chroma 向量库
"""
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
import hashlib

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False


class RAGIngestor:
    """RAG文档摄入器"""

    def __init__(self, source_dir: str = "./notes", persist_dir: str = "./.agentflow/chroma"):
        """
        初始化摄入器

        Args:
            source_dir: 文档源目录
            persist_dir: Chroma 持久化目录
        """
        self.source_dir = Path(source_dir)
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        # 支持的文件类型
        self.supported_extensions = {'.md', '.txt', '.pdf'}

        # Chroma 配置
        self.collection_name = "agent_documents"
        self.client = None
        self.collection = None
        self.embedding_model = None

        # 初始化
        self._initialize_chroma()
        self._initialize_embedding_model()

    def _initialize_chroma(self):
        """初始化 Chroma 客户端"""
        if not CHROMA_AVAILABLE:
            raise ImportError("ChromaDB 未安装，请运行: pip install chromadb")

        self.client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=Settings(anonymized_telemetry=False)
        )

        # 获取或创建集合
        try:
            self.collection = self.client.get_collection(name=self.collection_name)
            print(f"✅ 找到现有集合: {self.collection_name}")
        except Exception as e:
            # 集合不存在，创建新的
            print(f"创建新集合: {self.collection_name}")
            self.collection = self.client.create_collection(name=self.collection_name)

    def _initialize_embedding_model(self):
        """初始化嵌入模型"""
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            print("警告: SentenceTransformers 未安装，使用 Chroma 默认嵌入")
            return

        try:
            # 使用 all-MiniLM-L6-v2 模型
            self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            print("✅ 嵌入模型初始化成功: all-MiniLM-L6-v2")
        except Exception as e:
            print(f"警告: 嵌入模型加载失败 {e}，使用默认嵌入")
            self.embedding_model = None

    def _get_file_hash(self, file_path: Path) -> str:
        """计算文件哈希，用于检测文件变化"""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def _read_file_content(self, file_path: Path) -> Optional[str]:
        """读取文件内容"""
        try:
            if file_path.suffix.lower() == '.pdf':
                # PDF 文件暂时跳过
                print(f"跳过 PDF 文件: {file_path}")
                return None

            # 读取文本文件
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            return content

        except Exception as e:
            print(f"读取文件失败 {file_path}: {e}")
            return None

    def _chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        """
        将文本切分为重叠的块

        Args:
            text: 原始文本
            chunk_size: 块大小
            overlap: 重叠大小

        Returns:
            文本块列表
        """
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = start + chunk_size

            # 找到合适的断点（句号、换行等）
            if end < len(text):
                # 优先在句号后断开
                last_period = text.rfind('.', start, end)
                if last_period > start + chunk_size // 2:
                    end = last_period + 1
                else:
                    # 其次在换行符后断开
                    last_newline = text.rfind('\n', start, end)
                    if last_newline > start + chunk_size // 2:
                        end = last_newline

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            # 计算下一个块的起始位置（考虑重叠）
            start = end - overlap
            if start >= len(text):
                break

        return chunks

    def _create_chunks(self, content: str, file_path: Path) -> List[Dict[str, Any]]:
        """
        为文件内容创建块

        Args:
            content: 文件内容
            file_path: 文件路径

        Returns:
            块数据列表
        """
        chunks = self._chunk_text(content)
        file_hash = self._get_file_hash(file_path)

        chunk_data = []
        for i, chunk in enumerate(chunks):
            chunk_id = f"{file_path.relative_to(self.source_dir)}_{file_hash}_{i}"
            chunk_data.append({
                "id": chunk_id,
                "content": chunk,
                "metadata": {
                    "source": str(file_path.relative_to(self.source_dir)),
                    "file_path": str(file_path),
                    "file_hash": file_hash,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "chunk_size": len(chunk),
                    "ingested_at": time.time()
                }
            })

        return chunk_data

    def _is_file_ingested(self, file_path: Path, file_hash: str) -> bool:
        """检查文件是否已被摄入"""
        if not self.collection:
            return False

        try:
            # 查询该文件的块
            results = self.collection.get(
                where={"file_hash": file_hash}
            )
            return len(results['ids']) > 0
        except Exception as e:
            print(f"检查文件是否已摄入失败: {e}")
            return False

    def ingest_file(self, file_path: Path) -> int:
        """摄入单个文件"""
        print(f"处理文件: {file_path}")

        # 检查 collection 是否可用
        if not self.collection:
            print(f"❌ Collection 不可用，跳过文件: {file_path}")
            return 0

        # 检查文件类型
        if file_path.suffix.lower() not in self.supported_extensions:
            return 0

        # 读取文件内容
        content = self._read_file_content(file_path)
        if not content:
            return 0

        # 计算文件哈希
        file_hash = self._get_file_hash(file_path)

        # 检查是否已摄入
        if self._is_file_ingested(file_path, file_hash):
            print(f"文件已存在，跳过: {file_path}")
            return 0

        # 创建块
        chunks = self._create_chunks(content, file_path)
        if not chunks:
            return 0

        # 准备批量插入数据
        ids = [chunk["id"] for chunk in chunks]
        documents = [chunk["content"] for chunk in chunks]
        metadatas = [chunk["metadata"] for chunk in chunks]

        # 插入到 Chroma
        try:
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            print(f"✅ 摄入完成: {file_path} ({len(chunks)} 个块)")
            return len(chunks)
        except Exception as e:
            print(f"❌ 摄入失败: {file_path} - {e}")
            return 0

    def ingest_directory(self, force_reingest: bool = False) -> Dict[str, Any]:
        """
        摄入整个目录

        Args:
            force_reingest: 是否强制重新摄入

        Returns:
            摄入统计信息
        """
        if force_reingest:
            # 清空现有集合
            try:
                self.client.delete_collection(name=self.collection_name)
                self.collection = self.client.create_collection(name=self.collection_name)
                print("已清空现有索引")
            except Exception as e:
                print(f"清空索引失败: {e}")

        total_files = 0
        total_chunks = 0
        processed_files = 0

        # 递归遍历目录
        for file_path in self.source_dir.rglob('*'):
            if file_path.is_file():
                total_files += 1
                chunks_added = self.ingest_file(file_path)
                if chunks_added > 0:
                    processed_files += 1
                    total_chunks += chunks_added

        return {
            "total_files_found": total_files,
            "files_processed": processed_files,
            "total_chunks_added": total_chunks,
            "source_directory": str(self.source_dir),
            "persist_directory": str(self.persist_dir)
        }

    def get_stats(self) -> Dict[str, Any]:
        """获取摄入统计信息"""
        if not self.collection:
            return {
                "total_chunks": 0,
                "collection_name": self.collection_name,
                "persist_directory": str(self.persist_dir),
                "source_directory": str(self.source_dir),
                "status": "collection_not_initialized"
            }

        try:
            count = self.collection.count()
            return {
                "total_chunks": count,
                "collection_name": self.collection_name,
                "persist_directory": str(self.persist_dir),
                "source_directory": str(self.source_dir),
                "status": "ok"
            }
        except Exception as e:
            return {
                "error": str(e),
                "collection_name": self.collection_name,
                "persist_directory": str(self.persist_dir),
                "source_directory": str(self.source_dir),
                "status": "error"
            }


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="RAG 文档摄入工具")
    parser.add_argument("--src", default="./notes", help="文档源目录")
    parser.add_argument("--persist", default="./.agentflow/chroma", help="Chroma 持久化目录")
    parser.add_argument("--force", action="store_true", help="强制重新摄入")

    args = parser.parse_args()

    try:
        ingestor = RAGIngestor(args.src, args.persist)
        stats = ingestor.ingest_directory(force_reingest=args.force)

        print("\n=== 摄入完成统计 ===")
        print(f"发现文件总数: {stats['total_files_found']}")
        print(f"处理文件数: {stats['files_processed']}")
        print(f"新增块数: {stats['total_chunks_added']}")
        print(f"源目录: {stats['source_directory']}")
        print(f"存储目录: {stats['persist_directory']}")

    except Exception as e:
        print(f"摄入过程出错: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
