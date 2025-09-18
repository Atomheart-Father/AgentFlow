"""
标准工具返回结构定义
所有工具必须遵循此返回格式
"""
from typing import Dict, Any, Optional
from pydantic import BaseModel
from enum import Enum


class ErrorCode(str, Enum):
    """错误代码枚举"""
    NETWORK = "NETWORK"
    NOT_FOUND = "NOT_FOUND"
    INVALID_INPUT = "INVALID_INPUT"
    RATE_LIMIT = "RATE_LIMIT"
    INTERNAL = "INTERNAL"


class ToolError(BaseModel):
    """工具错误信息"""
    code: ErrorCode
    message: str
    retryable: bool = True


class ToolMeta(BaseModel):
    """工具调用元数据"""
    source: str  # 工具名称
    latency_ms: int
    params: Dict[str, Any]  # 调用参数


class StandardToolResult(BaseModel):
    """
    标准工具返回结构

    所有工具必须返回此格式，不得抛出未捕获异常
    """
    ok: bool
    data: Optional[Dict[str, Any]] = None  # 成功时的数据
    error: Optional[ToolError] = None      # 失败时的错误信息
    meta: ToolMeta                          # 元数据

    def __init__(self, **data):
        super().__init__(**data)
        # 验证结构完整性
        if self.ok and self.error is not None:
            raise ValueError("ok=True 时不能有error")
        if not self.ok and self.error is None:
            raise ValueError("ok=False 时必须有error")

    @classmethod
    def success(cls, data: Dict[str, Any], meta: ToolMeta) -> 'StandardToolResult':
        """创建成功结果"""
        return cls(ok=True, data=data, meta=meta)

    @classmethod
    def failure(cls, error: ToolError, meta: ToolMeta) -> 'StandardToolResult':
        """创建失败结果"""
        return cls(ok=False, error=error, meta=meta)

    def is_retryable(self) -> bool:
        """检查错误是否可重试"""
        return not self.ok and self.error.retryable if self.error else False


def create_tool_meta(source: str, latency_ms: int, params: Dict[str, Any]) -> ToolMeta:
    """创建工具元数据"""
    return ToolMeta(source=source, latency_ms=latency_ms, params=params)


def create_tool_error(code: ErrorCode, message: str, retryable: bool = True) -> ToolError:
    """创建工具错误"""
    return ToolError(code=code, message=message, retryable=retryable)
