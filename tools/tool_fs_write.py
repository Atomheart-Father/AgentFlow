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
        self.description = "安全地写入文件到指定位置，支持创建目录"
        self.parameters = {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径，可以是相对路径或特殊意图如'写到桌面'。相对路径相对于工作目录，'写到桌面'会自动映射到桌面目录"
                },
                "content": {
                    "type": "string",
                    "description": "要写入的文件内容"
                },
                "format": {
                    "type": "string",
                    "enum": ["md", "txt"],
                    "default": "md",
                    "description": "文件格式，影响文件扩展名"
                },
                "mkdirs": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否创建不存在的父目录"
                }
            },
            "required": ["path", "content"]
        }

        # 获取配置
        self.config = get_config()
        self.workspace_dir = Path.cwd()
        self.desktop_dir = self.config.desktop_dir_path

    def _normalize_path(self, path: str, format_type: str = "md") -> Path:
        """
        规范化路径

        Args:
            path: 输入路径
            format_type: 文件格式

        Returns:
            规范化的绝对路径

        Raises:
            ValueError: 路径不安全或无效
        """
        # 处理特殊意图
        if path.lower().strip() in ["写到桌面", "write to desktop", "desktop"]:
            # 生成智能文件名
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"document_{timestamp}.{format_type}"
            resolved_path = self.desktop_dir / filename
        else:
            # 解析相对路径
            path_obj = Path(path)

            # 安全检查：拒绝绝对路径和包含..的路径
            if path_obj.is_absolute():
                raise ValueError("不允许使用绝对路径")

            if ".." in path or path.startswith("/"):
                raise ValueError("路径包含非法字符或尝试路径穿越")

            # 检查是否是相对路径下的安全位置
            resolved_path = (self.workspace_dir / path_obj).resolve()

            # 确保路径在允许的目录下
            try:
                resolved_path.relative_to(self.workspace_dir)
            except ValueError:
                try:
                    resolved_path.relative_to(self.desktop_dir)
                except ValueError:
                    raise ValueError(f"路径必须在工作目录或桌面目录下: {path}")

            # 添加文件扩展名（如果没有）
            if not resolved_path.suffix:
                resolved_path = resolved_path.with_suffix(f".{format_type}")

        return resolved_path

    def _write_file(self, file_path: Path, content: str, mkdirs: bool = False) -> Dict[str, Any]:
        """
        写入文件

        Args:
            file_path: 文件路径
            content: 文件内容
            mkdirs: 是否创建目录

        Returns:
            写入结果信息
        """
        # 创建父目录（如果需要）
        if mkdirs and file_path.parent != file_path:
            file_path.parent.mkdir(parents=True, exist_ok=True)

        # 检查父目录是否存在
        if not file_path.parent.exists():
            if mkdirs:
                file_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                raise ValueError(f"父目录不存在: {file_path.parent}")

        # 写入文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # 获取文件信息
        stat = file_path.stat()
        return {
            "path_abs": str(file_path.absolute()),
            "bytes": stat.st_size,
            "modified_time": stat.st_mtime
        }

    def run(self, path: str, content: str, format: str = "md", mkdirs: bool = False) -> StandardToolResult:
        """
        写入文件

        Args:
            path: 文件路径
            content: 文件内容
            format: 文件格式
            mkdirs: 是否创建目录

        Returns:
            标准化的工具结果
        """
        start_time = time.time()

        try:
            # 规范化路径
            file_path = self._normalize_path(path, format)

            # 写入文件
            result = self._write_file(file_path, content, mkdirs)

            # 创建成功结果
            latency_ms = int((time.time() - start_time) * 1000)
            meta = create_tool_meta(self.name, latency_ms, {
                "path": path,
                "format": format,
                "mkdirs": mkdirs,
                "content_length": len(content)
            })

            return StandardToolResult.success(result, meta)

        except ValueError as e:
            # 输入验证错误
            latency_ms = int((time.time() - start_time) * 1000)
            error = create_tool_error(ErrorCode.INVALID_INPUT, str(e), retryable=False)
            meta = create_tool_meta(self.name, latency_ms, {
                "path": path,
                "format": format,
                "mkdirs": mkdirs
            })
            return StandardToolResult.failure(error, meta)

        except PermissionError as e:
            # 权限错误
            latency_ms = int((time.time() - start_time) * 1000)
            error = create_tool_error(ErrorCode.INTERNAL, f"权限不足: {str(e)}", retryable=False)
            meta = create_tool_meta(self.name, latency_ms, {
                "path": path,
                "format": format,
                "mkdirs": mkdirs
            })
            return StandardToolResult.failure(error, meta)

        except OSError as e:
            # 文件系统错误
            latency_ms = int((time.time() - start_time) * 1000)
            error = create_tool_error(ErrorCode.INTERNAL, f"文件系统错误: {str(e)}", retryable=True)
            meta = create_tool_meta(self.name, latency_ms, {
                "path": path,
                "format": format,
                "mkdirs": mkdirs
            })
            return StandardToolResult.failure(error, meta)

        except Exception as e:
            # 其他未知错误
            latency_ms = int((time.time() - start_time) * 1000)
            error = create_tool_error(ErrorCode.INTERNAL, f"写入失败: {str(e)}", retryable=True)
            meta = create_tool_meta(self.name, latency_ms, {
                "path": path,
                "format": format,
                "mkdirs": mkdirs
            })
            return StandardToolResult.failure(error, meta)
