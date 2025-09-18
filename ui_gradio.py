"""
Gradio用户界面
提供聊天界面，将用户输入传递给Agent核心处理
"""
import asyncio
import gradio as gr
from typing import List, Tuple, Dict, Any

from agent_core import create_agent_core_with_llm
from config import get_config
from logger import setup_logging, get_logger

# 初始化日志
config = get_config()
setup_logging(config.log_level)
logger = get_logger()


class ChatUI:
    """聊天UI类"""

    def __init__(self):
        self.config = config
        self.chat_history: List[Tuple[str, str]] = []
        self.metadata_history: List[Dict[str, Any]] = []
        # 创建带有LLM接口的Agent核心实例
        self.agent = create_agent_core_with_llm()

    def process_user_message(self, user_input: str, chat_history) -> Tuple[str, List[Tuple[str, str]], str]:
        """
        处理用户消息

        Args:
            user_input: 用户输入
            chat_history: 聊天历史

        Returns:
            清空的用户输入、更新后的聊天历史、工具轨迹文本
        """
        if not user_input.strip():
            return "", chat_history

        logger.info(f"收到用户输入: {user_input[:100]}{'...' if len(user_input) > 100 else ''}")

        try:
            # 调用Agent核心处理
            result = asyncio.run(self.agent.process(user_input))

            # 提取响应内容
            assistant_response = result["response"]
            metadata = result["metadata"]

            # 添加到聊天历史
            chat_history.append((user_input, assistant_response))

            # 记录元数据用于显示
            self.metadata_history.append(metadata)

            # 记录统计信息
            self._log_statistics(metadata)

            # 获取工具轨迹
            tool_trace_text = self.format_tool_trace(metadata.get("tool_call_trace", []))

            logger.info("用户消息处理完成")

        except Exception as e:
            error_msg = f"处理消息时发生错误: {str(e)}"
            logger.error(error_msg, exc_info=True)
            assistant_response = "抱歉，处理您的请求时出现了错误，请稍后重试。"
            chat_history.append((user_input, assistant_response))
            tool_trace_text = "❌ 处理过程中发生错误"

        return "", chat_history, tool_trace_text

    def _log_statistics(self, metadata: Dict[str, Any]):
        """记录统计信息"""
        if "response_time" in metadata:
            logger.info(f"响应时间: {metadata['response_time']:.2f}s")

        if "usage" in metadata and metadata["usage"]:
            usage = metadata["usage"]
            if "total_tokens" in usage:
                logger.info(f"Token使用: {usage['total_tokens']}")
            if "prompt_tokens" in usage:
                logger.info(f"输入Token: {usage['prompt_tokens']}")
            if "completion_tokens" in usage:
                logger.info(f"输出Token: {usage['completion_tokens']}")

    def clear_history(self, chat_history) -> Tuple[List[Tuple[str, str]], str, str]:
        """清除聊天历史"""
        logger.info("清除聊天历史")
        self.chat_history = []
        self.metadata_history = []
        return [], "聊天历史已清除", "工具轨迹已清除"

    def get_system_info(self) -> str:
        """获取系统信息"""
        provider_info = f"当前模型提供商: {self.config.model_provider}"
        if hasattr(self.config, 'deepseek_model'):
            provider_info += f" ({self.config.deepseek_model})"
        rag_status = f"RAG功能: {'启用' if self.config.rag_enabled else '禁用'}"
        tools_status = f"工具功能: {'启用' if self.config.tools_enabled else '禁用'} ({len(self.agent.tools) if hasattr(self, 'agent') else 0}个工具)"
        log_level = f"日志级别: {self.config.log_level}"

        return f"{provider_info}\n{rag_status}\n{tools_status}\n{log_level}"

    def format_tool_trace(self, tool_trace: list) -> str:
        """格式化工具调用轨迹"""
        if not tool_trace:
            return "本次对话未使用任何工具"

        trace_lines = ["🛠️ 工具调用轨迹:"]
        for i, trace in enumerate(tool_trace, 1):
            tool_name = trace.get("tool_name", "未知工具")
            execution_time = trace.get("execution_time", 0)
            success = not trace.get("error")

            status_icon = "✅" if success else "❌"
            trace_lines.append(f"{i}. {status_icon} {tool_name} ({execution_time:.2f}s)")

            if trace.get("error"):
                trace_lines.append(f"   错误: {trace['error'][:100]}...")

        return "\n".join(trace_lines)


def create_gradio_interface() -> gr.Blocks:
    """创建Gradio界面"""

    ui = ChatUI()

    with gr.Blocks(
        title="AI个人助理",
        theme=gr.themes.Soft(),
        css="""
        .gradio-container {
            max-width: 800px;
            margin: auto;
        }
        .chatbot {
            height: 500px;
        }
        """
    ) as interface:

        gr.Markdown("# 🤖 AI个人助理")
        gr.Markdown("*基于大语言模型的个人助手，目前支持基础对话功能*")

        # 系统信息显示
        with gr.Accordion("系统信息", open=False):
            system_info = gr.Textbox(
                value=ui.get_system_info(),
                interactive=False,
                lines=4,
                label="当前配置"
            )

        # 聊天界面
        chatbot = gr.Chatbot(
            height=500,
            show_label=False,
            container=True
        )

        # 工具轨迹面板
        with gr.Accordion("🛠️ 工具调用轨迹", open=False):
            tool_trace_display = gr.Textbox(
                value="本次对话未使用任何工具",
                interactive=False,
                lines=8,
                label="工具调用详情",
                show_label=False
            )

        # 输入框
        with gr.Row():
            user_input = gr.Textbox(
                placeholder="请输入您的问题...",
                show_label=False,
                container=False,
                scale=8
            )
            submit_btn = gr.Button("发送", scale=1, variant="primary")
            clear_btn = gr.Button("清除历史", scale=1)

        # 绑定事件
        submit_btn.click(
            ui.process_user_message,
            inputs=[user_input, chatbot],
            outputs=[user_input, chatbot, tool_trace_display]
        )

        user_input.submit(
            ui.process_user_message,
            inputs=[user_input, chatbot],
            outputs=[user_input, chatbot, tool_trace_display]
        )

        clear_btn.click(
            ui.clear_history,
            inputs=[chatbot],
            outputs=[chatbot, user_input, tool_trace_display]
        )

        # 页脚信息
        gr.Markdown("---")
        gr.Markdown("*提示：直接在输入框中输入问题并按Enter，或点击发送按钮*")

    return interface


def main():
    """主函数"""
    logger.info("启动Gradio UI...")

    try:
        interface = create_gradio_interface()

        # 启动服务器
        interface.launch(
            server_name="0.0.0.0",
            server_port=7860,
            share=False,
            show_error=True,
            inbrowser=True
        )

    except KeyboardInterrupt:
        logger.info("收到中断信号，正在关闭...")
    except Exception as e:
        logger.error(f"启动Gradio UI时发生错误: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
