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

            # 查找工具类
            # 首先尝试标准命名规则（模块名首字母大写）
            class_name = "".join(word.capitalize() for word in module_name.split("_"))

            # 特殊处理一些不规则的类名
            special_class_names = {
                "tool_date_utils": "ToolDateNormalizer",  # 特殊命名
                "tool_fs_write": "ToolFSWrite",           # 大小写问题
            }

            # 尝试多个可能的类名
            possible_class_names = [class_name]
            if module_name in special_class_names:
                possible_class_names.insert(0, special_class_names[module_name])

            tool_class = None
            for candidate_name in possible_class_names:
                if hasattr(module, candidate_name):
                    tool_class = getattr(module, candidate_name)
                    logger.debug(f"找到工具类: {candidate_name}")
                    break

            if tool_class:
                try:
                    tool_instance = tool_class()
                    tools.append(tool_instance)
                    logger.info(f"注册工具: {tool_instance.name}")
                except Exception as e:
                    logger.error(f"实例化工具失败 {candidate_name}: {e}")
            else:
                logger.warning(f"未找到工具类: {module_name} (尝试的类名: {possible_class_names})")

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


def execute_tool(tool_name: str, tools: List[Tool], **kwargs) -> 'StandardToolResult':
    """
    执行指定工具

    Args:
        tool_name: 工具名称
        tools: 可用工具列表
        **kwargs: 工具参数

    Returns:
        标准化的工具结果

    Raises:
        ToolError: 工具不存在或其他严重错误
    """
    from schemas.tool_result import StandardToolResult, ToolError as ToolResultError, create_tool_error, create_tool_meta, ErrorCode

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

        # 检查是否是异步方法
        import asyncio
        import inspect
        import time

        start_time = time.time()
        tool_timeout = self._get_tool_timeout(tool_name)

        if inspect.iscoroutinefunction(tool.run):
            # 异步方法，需要在事件循环中运行
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 如果事件循环已经在运行，使用线程池执行
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(asyncio.run, tool.run(**kwargs))
                        result = future.result(timeout=tool_timeout)
                else:
                    result = loop.run_until_complete(tool.run(**kwargs))
            except concurrent.futures.TimeoutError:
                logger.warning(f"工具 {tool_name} 执行超时 ({tool_timeout}s)")
                latency_ms = int((time.time() - start_time) * 1000)
                error = create_tool_error(ErrorCode.INTERNAL, f"工具执行超时 ({tool_timeout}s)", retryable=True)
                meta = create_tool_meta(tool_name, latency_ms, kwargs)
                return StandardToolResult.failure(error, meta)
            except Exception as async_e:
                logger.warning(f"异步执行失败，尝试同步执行: {async_e}")
                try:
                    result = tool.run(**kwargs)
                except Exception as sync_e:
                    logger.error(f"同步执行也失败: {sync_e}")
                    latency_ms = int((time.time() - start_time) * 1000)
                    error = create_tool_error(ErrorCode.INTERNAL, f"工具执行失败: {str(sync_e)}", retryable=True)
                    meta = create_tool_meta(tool_name, latency_ms, kwargs)
                    return StandardToolResult.failure(error, meta)
        else:
            # 同步方法，直接调用
            try:
                result = tool.run(**kwargs)
            except Exception as sync_e:
                logger.error(f"同步工具执行失败: {sync_e}")
                latency_ms = int((time.time() - start_time) * 1000)
                error = create_tool_error(ErrorCode.INTERNAL, f"工具执行失败: {str(sync_e)}", retryable=True)
                meta = create_tool_meta(tool_name, latency_ms, kwargs)
                return StandardToolResult.failure(error, meta)

        # 检查结果是否已经是StandardToolResult
        if isinstance(result, StandardToolResult):
            logger.info(f"工具 {tool_name} 执行成功")
            return result
        else:
            # 如果工具还没有更新为返回StandardToolResult，包装结果
            logger.warning(f"工具 {tool_name} 返回了非标准格式结果，正在包装")
            latency_ms = int((time.time() - start_time) * 1000)
            meta = create_tool_meta(tool_name, latency_ms, kwargs)
            return StandardToolResult.success({"result": result}, meta)

    except Exception as e:
        error_msg = f"工具执行失败: {str(e)}"
        logger.error(f"工具 {tool_name} 执行失败: {error_msg}")

        # 判断是否可重试（网络错误等通常可重试）
        retryable = "network" in str(e).lower() or "timeout" in str(e).lower()
        raise ToolError(tool_name, error_msg, retryable=retryable)

    def _get_tool_timeout(self, tool_name: str) -> float:
        """获取工具的超时时间"""
        # 为不同工具设置不同的超时时间
        timeouts = {
            "weather_get": 15.0,     # 天气查询15秒
            "time_now": 5.0,         # 时间查询5秒
            "file_read": 10.0,       # 文件读取10秒
            "fs_write": 10.0,        # 文件写入10秒
            "date_normalize": 3.0,   # 日期归一化3秒
            "calendar_read": 8.0,    # 日程读取8秒
            "email_list": 12.0,      # 邮件查询12秒
            "math_calc": 3.0,        # 数学计算3秒
        }
        return timeouts.get(tool_name, 10.0)  # 默认10秒

    def _get_tool_timeout_default(self, tool_name: str) -> Any:
        """获取工具超时的默认返回值"""
        defaults = {
            "weather_get": {"error": "天气查询超时，无法获取天气信息"},
            "time_now": {"error": "时间查询超时，无法获取当前时间"},
            "file_read": {"error": "文件读取超时，无法获取文件内容"},
            "fs_write": {"error": "文件写入超时，无法写入文件"},
            "calendar_read": {"error": "日程查询超时，无法获取日程信息"},
            "email_list": {"error": "邮件查询超时，无法获取邮件列表"},
            "math_calc": {"error": "数学计算超时，无法计算结果"},
        }
        return defaults.get(tool_name, {"error": f"工具 {tool_name} 执行超时"})


# 全局工具实例缓存
_cached_tools = None


def get_tools(whitelist: List[str] = None, use_cache: bool = True) -> List[Tool]:
    """
    获取工具实例（带缓存）

    Args:
        whitelist: 白名单工具列表
        use_cache: 是否使用缓存

    Returns:
        工具实例列表
    """
    global _cached_tools

    if not use_cache or _cached_tools is None:
        _cached_tools = _load_tools(whitelist)

    return _cached_tools


def _load_tools(whitelist: List[str] = None) -> List[Tool]:
    """加载工具实例"""
    tools = []

    # 动态导入工具模块
    tool_modules = [
        "tools.tool_weather",
        "tools.tool_time",
        "tools.tool_calculator",
        "tools.tool_calendar",
        "tools.tool_email",
        "tools.tool_file_reader",
        "tools.tool_file_writer",
        "tools.tool_fs_write",
        "tools.tool_math",
        "tools.tool_websearch",
        "tools.tool_datetime",
        "tools.tool_date_utils",
        "tools.tool_ask_user",
    ]

    for module_name in tool_modules:
        try:
            logger.debug(f"加载工具模块: {module_name}")
            module = __import__(module_name, fromlist=["ToolWeather", "ToolTime", "ToolCalculator", "ToolCalendar", "ToolEmail", "ToolFileReader", "ToolFileWriter", "ToolFSWrite", "ToolMath", "ToolWebSearch", "ToolDateTime", "ToolDateNormalizer", "ToolAskUser"])

            # 获取工具类
            tool_classes = []
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and
                    hasattr(attr, 'name') and
                    hasattr(attr, 'run')):
                    tool_classes.append(attr)

            # 实例化工具
            for tool_class in tool_classes:
                try:
                    if whitelist and tool_class.name not in whitelist:
                        continue

                    tool_instance = tool_class()
                    tools.append(tool_instance)
                    logger.info(f"注册工具: {tool_class.name}")
                except Exception as e:
                    logger.warning(f"实例化工具 {tool_class.__name__} 失败: {e}")

        except ImportError as e:
            logger.warning(f"导入工具模块 {module_name} 失败: {e}")
        except Exception as e:
            logger.error(f"加载工具模块 {module_name} 时发生错误: {e}")

    return tools


# 创建全局执行器实例
_executor_instance = None


def get_executor() -> "ToolExecutor":
    """获取全局工具执行器实例"""
    global _executor_instance
    if _executor_instance is None:
        _executor_instance = ToolExecutor()
    return _executor_instance


def execute_tool(tool_name: str, tools: List[Tool], **kwargs) -> Any:
    """
    执行工具

    Args:
        tool_name: 工具名称
        tools: 工具列表
        **kwargs: 工具参数

    Returns:
        工具执行结果
    """
    return get_executor().execute_tool(tool_name, tools, **kwargs)


class ToolExecutor:
    """工具执行器"""

    def execute_tool(self, tool_name: str, tools: List[Tool], **kwargs) -> Any:
        """
        执行工具

        Args:
            tool_name: 工具名称
            tools: 工具列表
            **kwargs: 工具参数

        Returns:
            工具执行结果
        """
        tool = None
        for t in tools:
            if t.name == tool_name:
                tool = t
                break

        if tool is None:
            raise ToolError(tool_name, f"工具不存在", retryable=False)

        try:
            logger.info(f"执行工具: {tool_name} 参数: {kwargs}")

            # 检查是否是异步方法
            import asyncio
            import inspect

            # 为不同工具设置不同的超时时间
            tool_timeout = self._get_tool_timeout(tool_name)

            if inspect.iscoroutinefunction(tool.run):
                # 异步方法，需要在事件循环中运行
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # 如果事件循环已经在运行，使用线程池执行
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            future = executor.submit(asyncio.run, tool.run(**kwargs))
                            result = future.result(timeout=tool_timeout)
                    else:
                        result = loop.run_until_complete(tool.run(**kwargs))
                except concurrent.futures.TimeoutError:
                    logger.warning(f"工具 {tool_name} 执行超时 ({tool_timeout}s)")
                    result = self._get_tool_timeout_default(tool_name)
                except Exception as async_e:
                    logger.warning(f"异步执行失败，尝试同步执行: {async_e}")
                    try:
                        result = tool.run(**kwargs)
                    except Exception as sync_e:
                        logger.error(f"同步执行也失败: {sync_e}")
                        result = self._get_tool_timeout_default(tool_name)
            else:
                # 同步方法，直接调用
                try:
                    result = tool.run(**kwargs)
                except Exception as sync_e:
                    logger.error(f"同步工具执行失败: {sync_e}")
                    result = self._get_tool_timeout_default(tool_name)

            logger.info(f"工具 {tool_name} 执行成功")
            return result

        except Exception as e:
            error_msg = f"工具执行失败: {str(e)}"
            logger.error(f"工具 {tool_name} 执行失败: {error_msg}")

            # 判断是否可重试（网络错误等通常可重试）
            retryable = "network" in str(e).lower() or "timeout" in str(e).lower()
            raise ToolError(tool_name, error_msg, retryable=retryable)

    def _get_tool_timeout(self, tool_name: str) -> float:
        """获取工具的超时时间"""
        # 为不同工具设置不同的超时时间
        timeouts = {
            "weather_get": 15.0,     # 天气查询15秒
            "time_now": 5.0,         # 时间查询5秒
            "file_read": 10.0,       # 文件读取10秒
            "fs_write": 10.0,        # 文件写入10秒
            "date_normalize": 3.0,   # 日期归一化3秒
            "calendar_read": 8.0,    # 日程读取8秒
            "email_list": 12.0,      # 邮件查询12秒
            "math_calc": 3.0,        # 数学计算3秒
        }
        return timeouts.get(tool_name, 10.0)  # 默认10秒

    def _get_tool_timeout_default(self, tool_name: str) -> Any:
        """获取工具超时的默认返回值"""
        defaults = {
            "weather_get": {"error": "天气查询超时，无法获取天气信息"},
            "time_now": {"error": "时间查询超时，无法获取当前时间"},
            "file_read": {"error": "文件读取超时，无法获取文件内容"},
            "fs_write": {"error": "文件写入超时，无法写入文件"},
            "calendar_read": {"error": "日程查询超时，无法获取日程信息"},
            "email_list": {"error": "邮件查询超时，无法获取邮件列表"},
            "math_calc": {"error": "数学计算超时，无法计算结果"},
        }
        return defaults.get(tool_name, {"error": f"工具 {tool_name} 执行超时"})


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
