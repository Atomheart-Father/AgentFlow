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

        # 模型分工配置
        self.planner_model = os.getenv("PLANNER_MODEL", "deepseek-reasoner")
        self.planner_temperature = float(os.getenv("PLANNER_TEMPERATURE", "0.2"))
        self.judge_model = os.getenv("JUDGE_MODEL", "deepseek-reasoner")
        self.judge_temperature = float(os.getenv("JUDGE_TEMPERATURE", "0.2"))
        self.executor_model = os.getenv("EXECUTOR_MODEL", "deepseek-chat")
        self.executor_temperature = float(os.getenv("EXECUTOR_TEMPERATURE", "0.1"))

        # 目录配置
        self.desktop_dir = os.getenv("DESKTOP_DIR", "~/Desktop/AgentFlow")
        # 解析桌面目录路径
        self.desktop_dir_path = Path(self.desktop_dir).expanduser().resolve()

        # 功能开关
        self.rag_enabled = os.getenv("RAG_ENABLED", "false").lower() == "true"
        self.tools_enabled = os.getenv("TOOLS_ENABLED", "false").lower() == "true"
        self.use_m3_orchestrator = os.getenv("USE_M3_ORCHESTRATOR", "true").lower() == "true"
        self.strict_json_mode = os.getenv("STRICT_JSON_MODE", "true").lower() == "true"

        # 日志配置
        self.log_level = os.getenv("LOG_LEVEL", "INFO")

        # LLM参数
        self.max_tokens = int(os.getenv("MAX_TOKENS", "4096"))
        self.temperature = float(os.getenv("TEMPERATURE", "0.7"))
        self.timeout_seconds = int(os.getenv("TIMEOUT_SECONDS", "30"))
        self.max_retries = int(os.getenv("MAX_RETRIES", "3"))

        # M3 Orchestrator 参数
        self.max_tool_calls_per_act = int(os.getenv("MAX_TOOL_CALLS_PER_ACT", "3"))
        self.max_total_tool_calls = int(os.getenv("MAX_TOTAL_TOOL_CALLS", "6"))
        self.max_plan_iters = int(os.getenv("MAX_PLAN_ITERS", "2"))
        self.max_latency_ms = int(os.getenv("MAX_LATENCY_MS", "20000"))
        self.max_tokens_per_stage = int(os.getenv("MAX_TOKENS_PER_STAGE", "4000"))

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

        # 验证分工模型
        valid_models = ["deepseek-chat", "deepseek-reasoner"]
        if self.planner_model not in valid_models:
            errors.append(f"无效的PLANNER_MODEL: {self.planner_model} (应为 {valid_models})")
        if self.judge_model not in valid_models:
            errors.append(f"无效的JUDGE_MODEL: {self.judge_model} (应为 {valid_models})")
        if self.executor_model not in valid_models:
            errors.append(f"无效的EXECUTOR_MODEL: {self.executor_model} (应为 {valid_models})")

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
