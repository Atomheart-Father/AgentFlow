"""
Agent核心模块
处理用户输入，协调LLM调用，目前只做直连LLM和日志记录
"""
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime

from llm_interface import get_llm_interface, LLMResponse
from config import get_config
from logger import get_logger

logger = get_logger()


class AgentCore:
    """Agent核心类"""

    def __init__(self, llm_interface=None):
        self.config = get_config()
        self.llm = llm_interface or get_llm_interface()
        logger.info("Agent核心初始化完成", extra={
            "provider": self.config.model_provider,
            "rag_enabled": self.config.rag_enabled,
            "tools_enabled": self.config.tools_enabled,
            "llm_initialized": self.llm.provider is not None
        })

    def set_llm_interface(self, llm_interface) -> None:
        """
        设置LLM接口

        Args:
            llm_interface: LLM接口实例
        """
        self.llm = llm_interface
        logger.info("LLM接口已更新", extra={
            "provider": self.config.model_provider,
            "llm_initialized": self.llm.provider is not None
        })

    async def process(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        处理用户输入

        Args:
            user_input: 用户输入文本
            context: 上下文信息（预留）

        Returns:
            Dict包含响应内容和元数据
        """
        if self.llm.provider is None:
            raise RuntimeError("LLM提供者未初始化。请先调用 set_llm_interface() 设置有效的LLM接口，或调用 llm.initialize_provider()")

        start_time = datetime.now()
        logger.info(f"开始处理用户输入: {user_input[:100]}{'...' if len(user_input) > 100 else ''}")

        try:
            # 构建提示词
            prompt = self._build_prompt(user_input, context)

            # 调用LLM（目前不使用工具）
            llm_response = await self.llm.generate(
                prompt=prompt,
                tools_schema=None  # 暂时不启用工具
            )

            # 记录响应信息
            self._log_response(llm_response, user_input)

            # 计算总处理时间
            total_time = (datetime.now() - start_time).total_seconds()

            logger.info(".2f")
            # 构建返回结果
            result = {
                "response": llm_response.content,
                "metadata": {
                    "model": llm_response.model,
                    "response_time": llm_response.response_time,
                    "total_time": total_time,
                    "usage": llm_response.usage,
                    "function_calls": llm_response.function_calls,
                    "timestamp": start_time.isoformat()
                }
            }

            return result

        except Exception as e:
            error_msg = f"处理用户输入时发生错误: {str(e)}"
            logger.error(error_msg, exc_info=True)

            return {
                "response": "抱歉，处理您的请求时出现了错误，请稍后重试。",
                "metadata": {
                    "error": str(e),
                    "timestamp": start_time.isoformat(),
                    "total_time": (datetime.now() - start_time).total_seconds()
                }
            }

    def _build_prompt(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        构建提示词

        Args:
            user_input: 用户输入
            context: 上下文信息

        Returns:
            完整的提示词
        """
        system_prompt = """你是AI个人助理，可以帮助用户处理各种任务。
目前你只具备基本的对话能力，其他功能正在开发中。

请用友好的语气回答用户的问题。"""

        if context:
            # 如果有上下文，添加到提示词中
            context_str = "\n".join([f"{k}: {v}" for k, v in context.items()])
            prompt = f"{system_prompt}\n\n上下文信息:\n{context_str}\n\n用户: {user_input}"
        else:
            prompt = f"{system_prompt}\n\n用户: {user_input}"

        return prompt

    def _log_response(self, llm_response: LLMResponse, user_input: str):
        """
        记录LLM响应信息

        Args:
            llm_response: LLM响应对象
            user_input: 用户输入
        """
        # 记录基本信息
        logger.info("LLM响应完成", extra={
            "model": llm_response.model,
            "response_time": ".2f",
            "content_length": len(llm_response.content),
            "has_function_calls": llm_response.function_calls is not None
        })

        # 如果启用DEBUG模式，记录更多详细信息
        if self.config.log_level == "DEBUG":
            logger.debug("详细响应信息", extra={
                "user_input": user_input[:200] + "..." if len(user_input) > 200 else user_input,
                "response_content": llm_response.content[:500] + "..." if len(llm_response.content) > 500 else llm_response.content,
                "usage": llm_response.usage,
                "function_calls": llm_response.function_calls
            })

        # 记录token使用情况
        if llm_response.usage:
            usage_info = []
            if "total_tokens" in llm_response.usage:
                usage_info.append(f"总token: {llm_response.usage['total_tokens']}")
            if "prompt_tokens" in llm_response.usage:
                usage_info.append(f"输入token: {llm_response.usage['prompt_tokens']}")
            if "completion_tokens" in llm_response.usage:
                usage_info.append(f"输出token: {llm_response.usage['completion_tokens']}")

            if usage_info:
                logger.info(f"Token使用情况: {' | '.join(usage_info)}")


# 全局实例（默认不初始化LLM，供独立测试使用）
agent_core = AgentCore()


def get_agent_core() -> AgentCore:
    """获取Agent核心实例"""
    return agent_core


def create_agent_core_with_llm() -> AgentCore:
    """创建带有LLM初始化的Agent核心实例"""
    from llm_interface import create_llm_interface_with_keys
    llm = create_llm_interface_with_keys()
    return AgentCore(llm_interface=llm)


async def process_message(user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    便捷函数：处理单个消息

    Args:
        user_input: 用户输入
        context: 上下文

    Returns:
        处理结果
    """
    return await agent_core.process(user_input, context)
