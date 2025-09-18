import os
import time
from pathlib import Path
from typing import Dict, Any
from config import get_config
from logger import get_logger
from schemas.tool_result import StandardToolResult, ToolMeta, ToolError, ErrorCode, create_tool_meta, create_tool_error

logger = get_logger()
config = get_config()

class ToolPathPlanner:
    def __init__(self):
        self.name = "path_planner"
        self.description = "根据配置文件中的输出目录和给定的文件名生成完整的文件路径。"
        self.parameters = {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "文件名（不含扩展名）"
                },
                "file_type": {
                    "type": "string",
                    "enum": ["md", "txt", "json", "pdf", "doc", "docx", "xls", "xlsx", "png", "jpg", "jpeg", "gif", "zip"],
                    "description": "文件类型，用于确定文件扩展名",
                    "default": "txt"
                }
            },
            "required": ["filename"]
        }

    def run(self, filename: str, file_type: str = "txt", **kwargs) -> StandardToolResult:
        """
        规划文件路径

        Args:
            filename: 文件名（不含扩展名）
            file_type: 文件类型

        Returns:
            标准化的工具结果
        """
        start_time = time.time()

        try:
            # 使用配置文件中的输出目录
            output_dir = config.desktop_dir_path

            # 构建完整文件名
            if not filename.lower().endswith(f".{file_type.lower()}"):
                full_filename = f"{filename}.{file_type}"
            else:
                full_filename = filename

            # 生成完整路径
            resolved_path = output_dir / full_filename

            # 验证路径安全性
            if not self._is_path_safe(resolved_path):
                error = create_tool_error(
                    ErrorCode.PERMISSION_DENIED,
                    f"不允许访问该路径: {resolved_path}",
                    retryable=False
                )
                meta = create_tool_meta(self.name, int((time.time() - start_time) * 1000),
                                      {"filename": filename, "file_type": file_type})
                return StandardToolResult.failure(error, meta)

            # 返回规划结果
            latency_ms = int((time.time() - start_time) * 1000)
            result = {
                "filename": filename,
                "file_type": file_type,
                "output_dir": str(output_dir),
                "resolved_path": str(resolved_path),
                "absolute_path": str(resolved_path.absolute()),
                "exists": resolved_path.exists(),
                "is_directory": resolved_path.is_dir() if resolved_path.exists() else False,
                "parent_exists": resolved_path.parent.exists()
            }

            meta = create_tool_meta(self.name, latency_ms,
                                  {"filename": filename, "file_type": file_type})
            return StandardToolResult.success(result, meta)

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            error = create_tool_error(
                ErrorCode.INTERNAL,
                f"路径规划失败: {str(e)}",
                retryable=False
            )
            meta = create_tool_meta(self.name, latency_ms,
                                  {"filename": filename, "file_type": file_type})
            return StandardToolResult.failure(error, meta)


    def _is_path_safe(self, path: Path) -> bool:
        """
        检查路径是否安全

        Args:
            path: 要检查的路径

        Returns:
            是否安全
        """
        try:
            # 解析绝对路径
            abs_path = path.absolute()

            # 允许的根目录
            allowed_roots = [
                Path.home(),
                config.desktop_dir_path,
                Path.cwd()
            ]

            # 检查是否在允许的目录下
            for root in allowed_roots:
                try:
                    abs_path.relative_to(root)
                    return True
                except ValueError:
                    continue

            return False

        except Exception:
            return False
