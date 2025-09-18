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
        self.description = "将自然语言路径描述转换为系统可用的文件路径。支持桌面、下载、文档等常见目录的智能映射。"
        self.parameters = {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "路径的自然语言描述，例如：'桌面上的报告文件'、'下载文件夹中的图片'、'我的文档文件夹'"
                },
                "filename": {
                    "type": "string",
                    "description": "文件名（可选），如果提供会自动添加合适的文件扩展名"
                },
                "file_type": {
                    "type": "string",
                    "enum": ["md", "txt", "json", "pdf", "doc", "docx", "xls", "xlsx", "png", "jpg", "jpeg", "gif", "zip"],
                    "description": "文件类型，用于确定文件扩展名",
                    "default": "txt"
                }
            },
            "required": ["description"]
        }

    def run(self, description: str, filename: str = None, file_type: str = "txt", **kwargs) -> StandardToolResult:
        """
        规划文件路径

        Args:
            description: 路径描述
            filename: 文件名（可选）
            file_type: 文件类型

        Returns:
            标准化的工具结果
        """
        start_time = time.time()

        try:
            # 解析路径描述
            resolved_path = self._parse_path_description(description, filename, file_type)

            # 验证路径安全性
            if not self._is_path_safe(resolved_path):
                error = create_tool_error(
                    ErrorCode.PERMISSION_DENIED,
                    f"不允许访问该路径: {resolved_path}",
                    retryable=False
                )
                meta = create_tool_meta(self.name, int((time.time() - start_time) * 1000),
                                      {"description": description, "filename": filename, "file_type": file_type})
                return StandardToolResult.failure(error, meta)

            # 返回规划结果
            latency_ms = int((time.time() - start_time) * 1000)
            result = {
                "original_description": description,
                "resolved_path": str(resolved_path),
                "absolute_path": str(resolved_path.absolute()),
                "exists": resolved_path.exists(),
                "is_directory": resolved_path.is_dir() if resolved_path.exists() else False,
                "parent_exists": resolved_path.parent.exists(),
                "file_type": file_type
            }

            meta = create_tool_meta(self.name, latency_ms,
                                  {"description": description, "filename": filename, "file_type": file_type})
            return StandardToolResult.success(result, meta)

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            error = create_tool_error(
                ErrorCode.INTERNAL,
                f"路径规划失败: {str(e)}",
                retryable=False
            )
            meta = create_tool_meta(self.name, latency_ms,
                                  {"description": description, "filename": filename, "file_type": file_type})
            return StandardToolResult.failure(error, meta)

    def _parse_path_description(self, description: str, filename: str = None, file_type: str = "txt") -> Path:
        """
        解析路径描述

        Args:
            description: 路径描述
            filename: 文件名
            file_type: 文件类型

        Returns:
            解析后的路径
        """
        desc_lower = description.lower().strip()

        # 获取基础目录
        base_path = Path.cwd()  # 当前工作目录
        desktop_path = config.desktop_dir_path

        # 智能路径映射
        if any(word in desc_lower for word in ["桌面", "desktop"]):
            target_dir = desktop_path
        elif any(word in desc_lower for word in ["下载", "downloads", "download"]):
            target_dir = Path.home() / "Downloads"
        elif any(word in desc_lower for word in ["文档", "documents", "document"]):
            target_dir = Path.home() / "Documents"
        elif any(word in desc_lower for word in ["图片", "图片", "images", "pictures"]):
            target_dir = Path.home() / "Pictures"
        elif any(word in desc_lower for word in ["工作", "workspace", "工作区"]):
            target_dir = base_path
        else:
            # 默认使用桌面
            target_dir = desktop_path

        # 如果没有指定文件名，生成一个
        if not filename:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"file_{timestamp}"

        # 确保有扩展名
        if not filename.lower().endswith(f".{file_type.lower()}"):
            filename = f"{filename}.{file_type}"

        return target_dir / filename

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
