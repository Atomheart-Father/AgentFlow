"""
LLM接口模块
统一封装对 Gemini 和 DeepSeek API 的调用
支持模型切换、超时重试、函数调用
"""
import json
import time
from typing import Optional, Dict, Any, List
from abc import ABC, abstractmethod

import google.generativeai as genai
from openai import OpenAI
import httpx
from pydantic import BaseModel

from config import get_config
from logger import get_logger

logger = get_logger()


class LLMResponse(BaseModel):
    """LLM响应模型"""
    content: str
    function_calls: Optional[List[Dict[str, Any]]] = None
    usage: Optional[Dict[str, int]] = None
    model: str
    response_time: float


class LLMProvider(ABC):
    """LLM提供者抽象基类"""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        tools_schema: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> LLMResponse:
        """生成响应"""
        pass


class GeminiProvider(LLMProvider):
    """Gemini提供者"""

    def __init__(self, api_key: str, model: str = "gemini-1.5-pro"):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model)
        self.model_name = model

    async def generate(
        self,
        prompt: str = "",
        messages: Optional[List[Dict[str, str]]] = None,
        tools_schema: Optional[List[Dict[str, Any]]] = None,
        force_json: bool = False,
        **kwargs
    ) -> LLMResponse:
        start_time = time.time()

        try:
            # 配置生成参数
            generation_config = genai.GenerationConfig(
                temperature=kwargs.get('temperature', 0.7),
                max_output_tokens=kwargs.get('max_tokens', 4096),
            )

            # 如果有工具，转换为Gemini格式
            tools = None
            if tools_schema:
                tools = [genai.protos.Tool(function_declarations=tools_schema)]

            # 创建模型实例
            if tools:
                model = genai.GenerativeModel(
                    self.model_name,
                    tools=tools,
                    generation_config=generation_config
                )
            else:
                model = genai.GenerativeModel(
                    self.model_name,
                    generation_config=generation_config
                )

            # 生成响应
            response = await model.generate_content_async(prompt)

            # 解析响应
            content = response.text if hasattr(response, 'text') else ""

            # 处理函数调用
            function_calls = []
            if hasattr(response, 'function_calls'):
                for call in response.function_calls:
                    function_calls.append({
                        "name": call.name,
                        "arguments": call.args if hasattr(call, 'args') else {}
                    })

            # 计算响应时间
            response_time = time.time() - start_time

            # 构建使用情况（Gemini没有直接的token计数）
            usage = {"estimated_tokens": len(content.split()) * 1.3}  # 粗略估计

            return LLMResponse(
                content=content,
                function_calls=function_calls if function_calls else None,
                usage=usage,
                model=self.model_name,
                response_time=response_time
            )

        except Exception as e:
            logger.error(f"Gemini API调用失败: {str(e)}")
            raise


class DeepSeekProvider(LLMProvider):
    """DeepSeek提供者"""

    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com", model: str = "deepseek-chat"):
        # 使用异步客户端
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        self.model = model

    async def generate(
        self,
        prompt: str = "",
        messages: Optional[List[Dict[str, str]]] = None,
        tools_schema: Optional[List[Dict[str, Any]]] = None,
        force_json: bool = False,
        **kwargs
    ) -> LLMResponse:
        start_time = time.time()

        try:
            # 构建消息
            if messages is None:
                messages = [{"role": "user", "content": prompt}]
            # 如果传入了messages，直接使用（确保是列表格式）
            elif not isinstance(messages, list):
                messages = [{"role": "user", "content": str(messages)}]

            # 构建工具参数
            tool_params = {}
            if tools_schema:
                tool_params["tools"] = tools_schema
                tool_params["tool_choice"] = "auto"

            # 处理JSON模式
            if force_json:
                tool_params["response_format"] = {"type": "json_object"}
                # 为JSON模式添加系统提示
                if not messages or messages[0]["role"] != "system":
                    messages.insert(0, {
                        "role": "system",
                        "content": "You must respond with valid JSON only."
                    })

            # 生成响应
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=kwargs.get('temperature', 0.7),
                max_tokens=kwargs.get('max_tokens', 4096),
                **tool_params
            )

            # 调试信息：打印DeepSeek的原始响应
            logger.debug(f"DeepSeek原始响应: {response}")
            logger.debug(f"消息内容: {response.choices[0].message.content}")
            if hasattr(response.choices[0].message, 'tool_calls') and response.choices[0].message.tool_calls:
                logger.debug(f"工具调用: {response.choices[0].message.tool_calls}")

            # 解析响应
            message = response.choices[0].message
            content = message.content or ""

            # 处理函数调用
            function_calls = []
            if hasattr(message, 'tool_calls') and message.tool_calls:
                for tool_call in message.tool_calls:
                    if tool_call.type == "function":
                        function_calls.append({
                            "id": tool_call.id,
                            "name": tool_call.function.name,
                            "arguments": json.loads(tool_call.function.arguments)
                        })

            # 计算响应时间
            response_time = time.time() - start_time

            # 获取使用情况
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }

            return LLMResponse(
                content=content,
                function_calls=function_calls if function_calls else None,
                usage=usage,
                model=self.model,
                response_time=response_time
            )

        except Exception as e:
            logger.error(f"DeepSeek API调用失败: {str(e)}")
            raise


class LLMInterface:
    """LLM接口统一封装"""

    def __init__(self, validate_keys=True):
        self.config = get_config()
        self.config.validate(require_api_keys=validate_keys)
        self.provider = None
        self.max_retries = self.config.max_retries
        self.timeout = self.config.timeout_seconds

        # 只有在需要验证密钥时才创建provider
        if validate_keys:
            self.provider = self._create_provider()

    def _create_provider(self) -> LLMProvider:
        """创建提供者实例"""
        if self.config.model_provider == "gemini":
            return GeminiProvider(
                api_key=self.config.gemini_api_key,
                model="gemini-1.5-pro"
            )
        elif self.config.model_provider == "deepseek":
            return DeepSeekProvider(
                api_key=self.config.deepseek_api_key,
                base_url=self.config.deepseek_base_url,
                model=self.config.deepseek_model
            )
        else:
            raise ValueError(f"不支持的提供者: {self.config.model_provider}")

    def initialize_provider(self):
        """初始化LLM提供者（需要有效的API密钥）"""
        if self.provider is None:
            self.config.validate(require_api_keys=True)  # 强制验证API密钥
            self.provider = self._create_provider()
            logger.info(f"LLM提供者已初始化: {self.config.model_provider}")

    async def generate(
        self,
        prompt: str = "",
        messages: Optional[List[Dict[str, str]]] = None,
        tools_schema: Optional[List[Dict[str, Any]]] = None,
        force_json: bool = False,
        **kwargs
    ) -> LLMResponse:
        """
        统一生成接口

        Args:
            prompt: 用户提示（当messages为None时使用）
            messages: 消息列表（优先于prompt）
            tools_schema: 工具模式（可选）
            force_json: 强制JSON输出模式（DeepSeek专用）
            **kwargs: 其他参数

        Returns:
            LLMResponse: 响应对象
        """
        if self.provider is None:
            raise RuntimeError("LLM提供者未初始化。请先调用 initialize_provider() 或在构造函数中设置 validate_keys=True")

        last_exception = None

        # 重试机制
        for attempt in range(self.max_retries + 1):
            try:
                logger.debug(f"LLM调用尝试 {attempt + 1}/{self.max_retries + 1}")

                # 设置超时
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    # 这里需要根据不同的provider设置client，但简化起见直接调用
                    # 准备参数，避免重复传递
                    provider_kwargs = {
                        "prompt": prompt,
                        "messages": messages,
                        "tools_schema": tools_schema,
                        "force_json": force_json,
                        "temperature": self.config.temperature,
                        "max_tokens": self.config.max_tokens,
                    }

                    # 如果kwargs中也有这些参数，优先使用kwargs的值
                    for key in ["temperature", "max_tokens"]:
                        if key in kwargs:
                            provider_kwargs[key] = kwargs[key]
                            del kwargs[key]

                    # 合并剩余的kwargs
                    provider_kwargs.update(kwargs)

                    return await self.provider.generate(**provider_kwargs)

            except Exception as e:
                last_exception = e
                logger.warning(f"LLM调用失败 (尝试 {attempt + 1}): {str(e)}")

                if attempt < self.max_retries:
                    # 指数退避重试
                    wait_time = 2 ** attempt
                    logger.info(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"LLM调用在 {self.max_retries + 1} 次尝试后仍然失败")
                    break

        # 所有重试都失败了
        raise last_exception or Exception("LLM调用失败")

    def get_provider_info(self) -> Dict[str, str]:
        """获取当前提供者信息"""
        return {
            "provider": self.config.model_provider,
            "model": getattr(self.provider, 'model_name', getattr(self.provider, 'model', 'unknown')),
            "timeout": str(self.timeout),
            "max_retries": str(self.max_retries)
        }


# 全局实例（默认不验证API密钥，供独立测试使用）
llm_interface = LLMInterface(validate_keys=False)


def get_llm_interface() -> LLMInterface:
    """获取LLM接口实例"""
    return llm_interface


def create_llm_interface_with_keys() -> LLMInterface:
    """创建带有API密钥验证的LLM接口实例"""
    return LLMInterface(validate_keys=True)
