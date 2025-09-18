"""
文件系统写入工具 - 安全的文件写入操作
支持写入到桌面目录或工作目录，包含路径安全检查
"""

import os
import time
from pathlib import Path
from typing import Dict, Any, Optional
from config import get_config
from schemas.tool_result import StandardToolResult, ToolError, ErrorCode, create_tool_meta, create_tool_error


class ToolFSWrite:
    """文件系统写入工具"""

    def __init__(self):
        self.name = "fs_write"
        self.description = "将文件内容写入到环境配置的目录中"
        self.parameters = {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "文件名（不含扩展名）"
                },
                "content": {
                    "type": "string",
                    "description": "要写入的文件内容"
                },
                "format": {
                    "type": "string",
                    "enum": ["md", "txt", "json"],
                    "default": "md",
                    "description": "文件格式，支持md、txt、json"
                }
            },
            "required": ["filename", "content"]
        }

        # 获取配置
        self.config = get_config()
        self.desktop_dir = self.config.desktop_dir_path

    def _generate_file_path(self, filename: str, format_type: str = "md") -> Path:
        """
        生成文件完整路径

        Args:
            filename: 文件名（不含扩展名）
            format_type: 文件格式

        Returns:
            完整的文件路径
        """
        # 构建完整文件名
        if not filename.lower().endswith(f".{format_type.lower()}"):
            full_filename = f"{filename}.{format_type}"
        else:
            full_filename = filename

        # 生成完整路径（直接拼接DESKTOP_DIR）
        file_path = self.desktop_dir / full_filename

        return file_path

    def _write_file(self, file_path: Path, content: str) -> Dict[str, Any]:
        """
        写入文件到配置的目录

        Args:
            file_path: 文件路径
            content: 文件内容

        Returns:
            写入结果信息

        Raises:
            ValueError: 写入失败
        """
        # 基本安全检查：不允许写目录
        if file_path.is_dir():
            raise ValueError("不能写入到目录")

        # 基本安全检查：不允许空内容
        if not content or not content.strip():
            raise ValueError("不允许写入空内容")

        # 基本安全检查：内容长度限制（防止DOS攻击）
        if len(content) > 10 * 1024 * 1024:  # 10MB
            raise ValueError("文件内容过大（最大10MB）")

        # 确保DESKTOP_DIR目录存在
        self.desktop_dir.mkdir(parents=True, exist_ok=True)

        # 写入文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # 获取文件信息
        stat = file_path.stat()
        return {
            "ok": True,
            "path_abs": str(file_path.absolute()),
            "bytes_written": stat.st_size
        }

    def run(self, filename: str, content: str, format: str = "md") -> StandardToolResult:
        """
        写入文件到配置的目录

        Args:
            filename: 文件名（不含扩展名）
            content: 文件内容
            format: 文件格式 (md, txt, json)

        Returns:
            标准化的工具结果 {ok, data, error, meta}
        """
        start_time = time.time()

        try:
            # 生成文件路径
            file_path = self._generate_file_path(filename, format)

            # 写入文件
            result = self._write_file(file_path, content)

            # 创建成功结果
            latency_ms = int((time.time() - start_time) * 1000)
            meta = create_tool_meta(self.name, latency_ms, {
                "filename": filename,
                "format": format,
                "content_length": len(content),
                "file_path": str(file_path)
            })

            return StandardToolResult.success(result, meta)

        except ValueError as e:
            # 验证错误
            latency_ms = int((time.time() - start_time) * 1000)
            error_code = "INVALID_INPUT"
            error = {
                "code": error_code,
                "message": str(e),
                "retryable": False
            }
            meta = create_tool_meta(self.name, latency_ms, {
                "filename": filename,
                "format": format
            })

            return StandardToolResult.failure(error, meta)

        except PermissionError as e:
            # 权限错误
            latency_ms = int((time.time() - start_time) * 1000)
            error = {
                "code": "PERMISSION_DENIED",
                "message": f"权限不足: {str(e)}",
                "retryable": False
            }
            meta = create_tool_meta(self.name, latency_ms, {
                "filename": filename,
                "format": format
            })
            return StandardToolResult.failure(error, meta)

        except OSError as e:
            # 文件系统错误
            latency_ms = int((time.time() - start_time) * 1000)
            error = {
                "code": "FILESYSTEM_ERROR",
                "message": f"文件系统错误: {str(e)}",
                "retryable": True
            }
            meta = create_tool_meta(self.name, latency_ms, {
                "filename": filename,
                "format": format
            })
            return StandardToolResult.failure(error, meta)

        except Exception as e:
            # 其他未知错误
            latency_ms = int((time.time() - start_time) * 1000)
            error = {
                "code": "INTERNAL_ERROR",
                "message": f"写入失败: {str(e)}",
                "retryable": True
            }
            meta = create_tool_meta(self.name, latency_ms, {
                "filename": filename,
                "format": format
            })
            return StandardToolResult.failure(error, meta)
