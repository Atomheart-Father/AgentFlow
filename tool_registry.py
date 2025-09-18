"""
工具注册模块
统一管理所有工具的注册、加载和调用
"""

import importlib
import inspect
from typing import Dict, Any, List, Protocol, Union
from pathlib import Path

from config import get_config
from logger import get_logger

logger = get_logger()


class ToolError(Exception):
    """工具调用错误"""
    def __init__(self, name: str, message: str, retryable: bool = False):
        self.name = name
        self.message = message
        self.retryable = retryable
        super().__init__(f"Tool '{name}' error: {message}")


class Tool(Protocol):
    """工具协议"""
    name: str
    description: str
    parameters: Dict[str, Any]

    def run(self, **kwargs) -> Union[Dict[str, Any], str]:
        """运行工具"""
        ...


def to_openai_tools(tools: List[Tool]) -> List[Dict[str, Any]]:
    """
    将工具转换为OpenAI格式

    Args:
        tools: 工具列表

    Returns:
        OpenAI格式的工具列表
    """
    openai_tools = []

    for tool in tools:
        tool_def = {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters
            }
        }
        openai_tools.append(tool_def)

    return openai_tools


def load_tools(whitelist: List[str] = None) -> List[Tool]:
    """
    从tools/目录动态加载工具

    Args:
        whitelist: 白名单工具名称列表，如果为None则加载所有工具

    Returns:
        工具实例列表
    """
    tools = []
    tools_dir = Path(__file__).parent / "tools"

    if not tools_dir.exists():
        logger.warning(f"工具目录不存在: {tools_dir}")
        return tools

    # 遍历tools目录中的Python文件
    for py_file in tools_dir.glob("tool_*.py"):
        module_name = py_file.stem  # tool_weather -> tool_weather

        try:
            # 动态导入模块
            module = importlib.import_module(f"tools.{module_name}")
            logger.debug(f"加载工具模块: {module_name}")

            # 查找工具类（假设类名是模块名的首字母大写版本）
            class_name = "".join(word.capitalize() for word in module_name.split("_"))
            if hasattr(module, class_name):
                tool_class = getattr(module, class_name)
                tool_instance = tool_class()
                tools.append(tool_instance)
                logger.info(f"注册工具: {tool_instance.name}")

        except Exception as e:
            logger.error(f"加载工具模块失败 {module_name}: {e}")
            continue

    # 如果有白名单，则过滤工具
    if whitelist:
        filtered_tools = []
        whitelist_set = set(whitelist)
        for tool in tools:
            if tool.name in whitelist_set:
                filtered_tools.append(tool)
        tools = filtered_tools
        logger.info(f"应用白名单过滤，剩余工具: {[t.name for t in tools]}")

    return tools


def execute_tool(tool_name: str, tools: List[Tool], **kwargs) -> Union[Dict[str, Any], str]:
    """
    执行指定工具

    Args:
        tool_name: 工具名称
        tools: 可用工具列表
        **kwargs: 工具参数

    Returns:
        工具执行结果

    Raises:
        ToolError: 工具执行失败
    """
    # 查找工具
    tool = None
    for t in tools:
        if t.name == tool_name:
            tool = t
            break

    if tool is None:
        raise ToolError(tool_name, f"工具不存在", retryable=False)

    try:
        logger.info(f"执行工具: {tool_name} 参数: {kwargs}")
        result = tool.run(**kwargs)
        logger.info(f"工具 {tool_name} 执行成功")
        return result

    except Exception as e:
        error_msg = f"工具执行失败: {str(e)}"
        logger.error(f"工具 {tool_name} 执行失败: {error_msg}")

        # 判断是否可重试（网络错误等通常可重试）
        retryable = "network" in str(e).lower() or "timeout" in str(e).lower()
        raise ToolError(tool_name, error_msg, retryable=retryable)


# 全局工具实例缓存
_cached_tools = None


def get_tools(whitelist: List[str] = None, use_cache: bool = True) -> List[Tool]:
    """
    获取工具实例（带缓存）

    Args:
        whitelist: 白名单
        use_cache: 是否使用缓存

    Returns:
        工具实例列表
    """
    global _cached_tools

    if use_cache and _cached_tools is not None:
        return _cached_tools

    _cached_tools = load_tools(whitelist)
    return _cached_tools


def get_tool_names() -> List[str]:
    """获取所有可用工具名称"""
    tools = get_tools()
    return [tool.name for tool in tools]


if __name__ == "__main__":
    # 测试代码
    logger.info("测试工具注册系统...")

    # 加载所有工具
    tools = load_tools()
    logger.info(f"加载了 {len(tools)} 个工具: {[t.name for t in tools]}")

    # 转换为OpenAI格式
    if tools:
        openai_format = to_openai_tools(tools)
        logger.info(f"OpenAI格式工具数量: {len(openai_format)}")
        logger.info("第一个工具定义示例:")
        logger.info(f"第一个工具定义示例: {openai_format[0] if openai_format else '无工具'}")
