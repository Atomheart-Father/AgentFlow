"""
文件写入工具 - 写入内容到本地文件
"""

from pathlib import Path
from typing import Dict, Any
import os


class ToolFileWriter:
    """文件写入工具"""

    def __init__(self):
        self.name = "file_write"
        self.description = "写入内容到本地文件，支持创建新文件或覆盖现有文件。支持路径别名：桌面、下载、文档、图片、音乐、视频等"
        self.parameters = {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件路径，支持绝对路径、相对路径和路径别名（如'桌面/报告.md'、'下载/文件.txt'等）"
                },
                "content": {
                    "type": "string",
                    "description": "要写入的文件内容"
                },
                "encoding": {
                    "type": "string",
                    "description": "文件编码格式，默认utf-8",
                    "default": "utf-8"
                },
                "create_dirs": {
                    "type": "boolean",
                    "description": "如果父目录不存在是否创建，默认true",
                    "default": True
                },
                "mode": {
                    "type": "string",
                    "description": "写入模式，'w'覆盖写入，'a'追加写入，默认'w'",
                    "default": "w",
                    "enum": ["w", "a"]
                }
            },
            "required": ["file_path", "content"]
        }

    def _resolve_path(self, file_path: str) -> Path:
        """
        解析文件路径，支持常见的路径别名

        Args:
            file_path: 输入的文件路径

        Returns:
            解析后的Path对象
        """
        # 处理常见的中文路径别名
        path_aliases = {
            "桌面": "~/Desktop",
            "下载": "~/Downloads",
            "文档": "~/Documents",
            "图片": "~/Pictures",
            "音乐": "~/Music",
            "视频": "~/Movies",
            "主目录": "~",
            "home": "~",
            "根目录": "/",
            "root": "/"
        }

        # 检查是否是路径别名
        for alias, real_path in path_aliases.items():
            if alias in file_path:
                file_path = file_path.replace(alias, real_path)
                break

        # 展开用户目录
        if "~" in file_path:
            file_path = os.path.expanduser(file_path)

        return Path(file_path)

    def run(self, file_path: str, content: str, encoding: str = "utf-8",
            create_dirs: bool = True, mode: str = "w", **kwargs) -> Dict[str, Any]:
        """
        写入内容到文件

        Args:
            file_path: 文件路径，支持路径别名（如"桌面"、"下载"等）
            content: 要写入的内容
            encoding: 文件编码
            create_dirs: 是否创建父目录
            mode: 写入模式 ('w'覆盖, 'a'追加)
            **kwargs: 其他参数

        Returns:
            写入结果信息
        """
        try:
            # 解析路径（支持别名）
            path = self._resolve_path(file_path)

            # 创建父目录（如果需要）
            if create_dirs and path.parent != path:  # 避免根目录
                path.parent.mkdir(parents=True, exist_ok=True)

            # 检查写入模式
            if mode not in ['w', 'a']:
                mode = 'w'

            # 写入文件
            with open(path, mode, encoding=encoding) as f:
                f.write(content)

            # 获取文件信息
            stat = path.stat()

            return {
                "file_path": str(path.absolute()),
                "file_name": path.name,
                "file_size": stat.st_size,
                "encoding": encoding,
                "mode": mode,
                "content_length": len(content),
                "created": mode == 'w',  # 覆盖模式认为是创建/更新
                "message": f"文件已成功写入: {path.absolute()}"
            }

        except Exception as e:
            raise ValueError(f"文件写入失败: {e}")
