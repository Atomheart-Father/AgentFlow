"""
主启动文件
启动AI个人助理系统
"""
import sys
import argparse

from config import get_config
from logger import setup_logging, get_logger

# 初始化配置和日志
config = get_config()
logger = setup_logging(config.log_level)


def start_ui():
    """启动Gradio UI"""
    logger.info("启动Gradio用户界面...")
    try:
        from ui_gradio import main as ui_main
        ui_main()
    except ImportError as e:
        logger.error(f"无法导入Gradio UI模块: {e}")
        logger.info("请确保已安装所有依赖: pip install -r requirements.txt")
        sys.exit(1)


def validate_config(require_api_keys=True):
    """验证配置"""
    try:
        config.validate(require_api_keys=require_api_keys)
        if require_api_keys:
            logger.info("配置验证通过（包含API密钥）")
        else:
            logger.info("配置验证通过（不包含API密钥）")
        return True
    except ValueError as e:
        logger.error(f"配置验证失败: {e}")
        if require_api_keys:
            logger.info("请检查.env文件或环境变量设置")
        return False


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="AI个人助理")
    parser.add_argument(
        "--ui",
        choices=["gradio"],
        default="gradio",
        help="选择要启动的UI界面 (默认: gradio)"
    )
    parser.add_argument(
        "--validate-config",
        action="store_true",
        help="仅验证配置，不启动服务"
    )
    parser.add_argument(
        "--validate-keys",
        action="store_true",
        help="验证API密钥（需要有效的API密钥）"
    )

    args = parser.parse_args()

    # 验证配置
    require_keys = args.validate_keys  # 只有明确指定 --validate-keys 时才验证API密钥
    if not validate_config(require_api_keys=require_keys):
        sys.exit(1)

    if args.validate_config:
        logger.info("配置验证完成")
        return

    # 如果需要验证密钥，初始化LLM
    if args.validate_keys:
        try:
            from llm_interface import create_llm_interface_with_keys
            llm = create_llm_interface_with_keys()
            logger.info("LLM接口初始化成功")
        except Exception as e:
            logger.error(f"LLM接口初始化失败: {e}")
            sys.exit(1)

    # 显示系统信息
    logger.info("=== AI个人助理启动 ===")
    logger.info(f"模型提供商: {config.model_provider}")
    logger.info(f"RAG功能: {'启用' if config.rag_enabled else '禁用'}")
    logger.info(f"工具功能: {'启用' if config.tools_enabled else '禁用'}")
    logger.info(f"日志级别: {config.log_level}")
    logger.info("=" * 30)

    # 启动对应的UI
    if args.ui == "gradio":
        start_ui()
    else:
        logger.error(f"不支持的UI类型: {args.ui}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在关闭...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"程序运行时发生错误: {e}", exc_info=True)
        sys.exit(1)
