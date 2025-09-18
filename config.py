"""
配置管理模块
从环境变量读取配置，支持.env文件
"""
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv


class Config:
    """配置类"""

    def __init__(self):
        # 加载.env文件
        env_path = Path(__file__).parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)

        # LLM配置
        self.model_provider = os.getenv("MODEL_PROVIDER", "deepseek")
        self.deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")  # deepseek-chat 或 deepseek-reasoner
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.deepseek_base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

        # 功能开关
        self.rag_enabled = os.getenv("RAG_ENABLED", "false").lower() == "true"
        self.tools_enabled = os.getenv("TOOLS_ENABLED", "false").lower() == "true"

        # 日志配置
        self.log_level = os.getenv("LOG_LEVEL", "INFO")

        # LLM参数
        self.max_tokens = int(os.getenv("MAX_TOKENS", "4096"))
        self.temperature = float(os.getenv("TEMPERATURE", "0.7"))
        self.timeout_seconds = int(os.getenv("TIMEOUT_SECONDS", "30"))
        self.max_retries = int(os.getenv("MAX_RETRIES", "3"))

    def validate(self, require_api_keys=True):
        """验证配置

        Args:
            require_api_keys: 是否要求API密钥（用于独立测试时可设为False）
        """
        errors = []

        if self.model_provider not in ["gemini", "deepseek"]:
            errors.append(f"无效的MODEL_PROVIDER: {self.model_provider}")

        if require_api_keys:
            # 验证当前选择的提供商是否有对应的API密钥
            if self.model_provider == "gemini" and not self.gemini_api_key:
                errors.append("GEMINI_API_KEY 未设置")

            if self.model_provider == "deepseek" and not self.deepseek_api_key:
                errors.append("DEEPSEEK_API_KEY 未设置")

            # 如果两个key都设置了，给出提示但不报错
            if self.gemini_api_key and self.deepseek_api_key:
                pass  # 两个key都设置了，这是允许的

        if self.log_level not in ["INFO", "DEBUG"]:
            errors.append(f"无效的LOG_LEVEL: {self.log_level}")

        # 验证DeepSeek模型选择
        if self.model_provider == "deepseek" and self.deepseek_model not in ["deepseek-chat", "deepseek-reasoner"]:
            errors.append(f"无效的DEEPSEEK_MODEL: {self.deepseek_model} (应为 deepseek-chat 或 deepseek-reasoner)")

        if errors:
            raise ValueError("配置错误: " + ", ".join(errors))

    def get_available_providers(self):
        """获取可用的提供商列表"""
        available = []
        if self.gemini_api_key:
            available.append("gemini")
        if self.deepseek_api_key:
            available.append("deepseek")
        return available


# 全局配置实例
config = Config()


def get_config() -> Config:
    """获取配置实例"""
    return config
