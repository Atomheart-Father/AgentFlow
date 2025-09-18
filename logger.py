"""
日志系统配置
支持 INFO 和 DEBUG 两档日志级别
"""
import os
import sys
from loguru import logger
from pathlib import Path


def setup_logging(log_level: str = "INFO", log_file: str = "logs/agent.log"):
    """
    设置日志系统

    Args:
        log_level: 日志级别 (INFO 或 DEBUG)
        log_file: 日志文件路径
    """
    # 移除默认的处理器
    logger.remove()

    # 设置日志级别
    level = log_level.upper()
    if level not in ["INFO", "DEBUG"]:
        level = "INFO"

    # 创建日志目录
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # 控制台输出格式
    console_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    # 文件输出格式 (更详细)
    file_format = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
        "{name}:{function}:{line} | {message}"
    )

    # 添加控制台处理器
    logger.add(
        sys.stdout,
        level=level,
        format=console_format,
        colorize=True,
        enqueue=True
    )

    # 添加文件处理器
    logger.add(
        log_file,
        level=level,
        format=file_format,
        rotation="10 MB",  # 文件大小超过10MB时轮转
        retention="1 week",  # 保留1周的日志
        encoding="utf-8",
        enqueue=True
    )

    # 设置第三方库的日志级别为WARNING，避免过多噪声
    import logging
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    logger.info(f"日志系统初始化完成，级别: {level}")
    return logger


def get_logger():
    """获取日志器实例"""
    return logger
