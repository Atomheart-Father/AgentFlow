"""
文件读取工具 - 读取本地文件内容
"""

from pathlib import Path
from typing import Dict, Any
import mimetypes


class ToolFileReader:
    """文件读取工具"""

    def __init__(self):
        self.name = "file.read"
        self.description = "读取本地文件内容，支持文本文件（.txt, .md, .py等）和PDF文件"
        self.parameters = {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件路径，支持绝对路径或相对路径"
                },
                "max_length": {
                    "type": "integer",
                    "description": "读取的最大字符数，默认10000",
                    "default": 10000
                },
                "encoding": {
                    "type": "string",
                    "description": "文件编码格式，默认utf-8",
                    "default": "utf-8"
                }
            },
            "required": ["file_path"]
        }

        # 支持的文件类型
        self.supported_text_types = [
            '.txt', '.md', '.py', '.js', '.html', '.css', '.json', '.xml', '.yaml', '.yml',
            '.csv', '.log', '.ini', '.cfg', '.conf', '.sh', '.bat', '.ps1'
        ]

        self.supported_binary_types = ['.pdf']

    def _read_text_file(self, file_path: Path, max_length: int, encoding: str) -> Dict[str, Any]:
        """
        读取文本文件

        Args:
            file_path: 文件路径
            max_length: 最大读取长度
            encoding: 文件编码

        Returns:
            文件内容信息
        """
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read(max_length)

            # 检查是否被截断
            was_truncated = False
            if len(content) == max_length:
                try:
                    # 尝试读取一个字符来检查是否还有更多内容
                    next_char = f.read(1)
                    if next_char:
                        was_truncated = True
                except:
                    pass

            return {
                "content": content,
                "truncated": was_truncated,
                "length": len(content),
                "encoding": encoding
            }

        except UnicodeDecodeError:
            raise ValueError(f"文件编码错误，请尝试其他编码格式")
        except Exception as e:
            raise ValueError(f"读取文本文件失败: {e}")

    def _read_pdf_file(self, file_path: Path, max_length: int) -> Dict[str, Any]:
        """
        读取PDF文件

        Args:
            file_path: 文件路径
            max_length: 最大读取长度

        Returns:
            PDF内容信息
        """
        try:
            import pypdf
        except ImportError:
            raise ValueError("PDF读取需要安装pypdf库: pip install pypdf")

        try:
            with open(file_path, 'rb') as f:
                pdf_reader = pypdf.PdfReader(f)
                content = ""

                # 读取所有页面
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    if len(content) + len(page_text) > max_length:
                        # 如果超出长度限制，截断内容
                        remaining_length = max_length - len(content)
                        content += page_text[:remaining_length]
                        break
                    content += page_text + "\n"

                return {
                    "content": content,
                    "pages": len(pdf_reader.pages),
                    "truncated": len(content) >= max_length,
                    "length": len(content)
                }

        except Exception as e:
            raise ValueError(f"读取PDF文件失败: {e}")

    def run(self, file_path: str, max_length: int = 10000, encoding: str = "utf-8", **kwargs) -> Dict[str, Any]:
        """
        读取文件内容

        Args:
            file_path: 文件路径
            max_length: 最大读取长度
            encoding: 文件编码
            **kwargs: 其他参数

        Returns:
            文件内容
        """
        try:
            # 转换为Path对象
            path = Path(file_path)

            # 检查文件是否存在
            if not path.exists():
                raise ValueError(f"文件不存在: {file_path}")

            # 检查是否是文件
            if not path.is_file():
                raise ValueError(f"路径不是文件: {file_path}")

            # 获取文件类型
            file_extension = path.suffix.lower()
            mime_type, _ = mimetypes.guess_type(str(path))

            result = {
                "file_path": str(path.absolute()),
                "file_name": path.name,
                "file_size": path.stat().st_size,
                "file_type": mime_type or "unknown",
                "file_extension": file_extension
            }

            # 根据文件类型选择读取方式
            if file_extension in self.supported_text_types:
                # 文本文件
                content_info = self._read_text_file(path, max_length, encoding)
                result.update(content_info)
                result["content_type"] = "text"

            elif file_extension in self.supported_binary_types:
                # 支持的二进制文件（PDF）
                if file_extension == '.pdf':
                    content_info = self._read_pdf_file(path, max_length)
                    result.update(content_info)
                    result["content_type"] = "pdf"
                else:
                    raise ValueError(f"不支持的文件类型: {file_extension}")

            else:
                raise ValueError(f"不支持的文件类型: {file_extension} (支持: {', '.join(self.supported_text_types + self.supported_binary_types)})")

            return result

        except Exception as e:
            raise ValueError(f"文件读取失败: {e}")
