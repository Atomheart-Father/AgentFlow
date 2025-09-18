# 🤖 AI Personal Assistant - M0 Phase

A personal AI assistant based on large language models, currently in M0 phase (runnable skeleton), supporting basic conversation functionality.

## ✨ Features

- **Multi-Model Support**: Support switching between Gemini and DeepSeek models
- **Unified Interface**: Unified LLM calling interface with timeout retry
- **Complete Logging**: INFO/DEBUG level logging, supporting file and console output
- **Flexible Configuration**: Configure through environment variables and .env file
- **Modern UI**: Chat interface based on Gradio
- **Modular Design**: Clear code structure for easy extension

## 🚀 Quick Start

### 1. Environment Setup

```bash
# Clone or download the project locally
cd /path/to/personal_agent

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure API Keys

Copy and edit the configuration file:

```bash
cp .env.example .env
```

Edit the `.env` file and set your API keys:

```env
# Choose model provider
MODEL_PROVIDER=gemini  # or deepseek

# Gemini configuration
GEMINI_API_KEY=your_gemini_api_key_here

# DeepSeek configuration
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com

# Other configurations can remain default
```

### 3. Start the System

```bash
# Start Gradio interface
python main.py

# Or run UI directly
python ui_gradio.py
```

The system will start at `http://localhost:7860`, and you can access the chat interface in your browser.

## 📁 Project Structure

```
personal_agent/
├── main.py                 # Main startup file
├── requirements.txt        # Dependencies list
├── .env.example           # Configuration template
├── README.md              # Documentation
├── config.py              # Configuration management
├── logger.py              # Logging system
├── llm_interface.py       # LLM interface abstraction
├── agent_core.py          # Agent core logic
├── ui_gradio.py           # Gradio user interface
├── rag_vector_store.py    # RAG retrieval module (reserved)
├── tool_registry.py       # Tool registration module (reserved)
├── tools/                 # Tool scripts directory
│   ├── tool_weather.py    # Weather query tool (reserved)
│   ├── tool_datetime.py   # Date time tool (reserved)
│   ├── tool_calculator.py # Calculator tool (reserved)
│   ├── tool_calendar.py   # Calendar query tool (reserved)
│   ├── tool_email.py      # Email reading tool (reserved)
│   ├── tool_websearch.py  # Web search tool (reserved)
│   └── tool_file_reader.py # File reading tool (reserved)
└── bot_telegram.py        # Telegram Bot (reserved)
```

## ⚙️ Configuration Guide

### API Key Setup

**📍 Location: `.env` file in project root directory**

1. Copy the configuration file:
```bash
cp .env.example .env
```

2. Edit the `.env` file and set your API keys:

```env
# Choose model provider to use
MODEL_PROVIDER=gemini  # or deepseek

# Set API keys (choose one or set all)
GEMINI_API_KEY=your_Gemini_API_key
DEEPSEEK_API_KEY=your_DeepSeek_API_key
```

### Complete Environment Variables List

| Variable Name | Default Value | Description |
|---------------|---------------|-------------|
| `MODEL_PROVIDER` | `gemini` | Model provider: `gemini` or `deepseek` |
| `GEMINI_API_KEY` | - | **Required**: Gemini API key |
| `DEEPSEEK_API_KEY` | - | **Required**: DeepSeek API key |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek API address |
| `RAG_ENABLED` | `false` | Enable RAG functionality |
| `TOOLS_ENABLED` | `false` | Enable tool functionality |
| `LOG_LEVEL` | `INFO` | Log level: `INFO` or `DEBUG` |
| `MAX_TOKENS` | `4096` | Maximum token count |
| `TEMPERATURE` | `0.7` | Generation temperature |
| `TIMEOUT_SECONDS` | `30` | Request timeout time |
| `MAX_RETRIES` | `3` | Maximum retry count |

### 🔑 Getting API Keys

- **Gemini API Key**:
  - Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
  - Create a new API key
  - **Note**: Free version has strict quota limits, may need to upgrade to paid version

- **DeepSeek API Key**:
  - Visit [DeepSeek Platform](https://platform.deepseek.com/)
  - Register account and create API key
  - **Recommended**: DeepSeek provides very cheap API pricing

### ⚠️ API Quota Notes

- **Gemini Free Version**: Has strict request frequency and daily limits
- **DeepSeek**: Provides more generous free quota, recommended for priority use
- If you encounter quota limits, you can switch `MODEL_PROVIDER` to another model in the `.env` file

### Logging System

Log files are saved in `logs/agent.log`, supporting:
- Console output (colored)
- File output (structured)
- Auto rotation (10MB)
- Retention for 7 days

## 🔧 Development Guide

### Independent Testing of Each Feature

The system is designed to support independent testing in notebooks without complete API key setup:

```python
# 1. Test configuration system
from config import get_config
config = get_config()
config.validate(require_api_keys=False)  # Don't validate API keys

# 2. Test logging system
from logger import setup_logging, get_logger
setup_logging("DEBUG")
logger = get_logger()

# 3. Test LLM interface (requires API keys)
from llm_interface import create_llm_interface_with_keys
llm = create_llm_interface_with_keys()
await llm.generate("Hello, world!")

# 4. Test Agent core
from agent_core import AgentCore
agent = AgentCore()
agent.set_llm_interface(llm)  # Set LLM interface
result = await agent.process("Hello")
```

### Adding New LLM Providers

1. Inherit `LLMProvider` class in `llm_interface.py`
2. Implement `generate` method
3. Add new provider in `LLMInterface._create_provider()`

### Extending Agent Functionality

1. Add new logic in `process` method of `agent_core.py`
2. Implement tool calling and RAG retrieval
3. Update configuration switches

### Customizing UI

Modify interface layout and styles in `ui_gradio.py`.

## 📝 Usage Instructions

1. **Basic Conversation**: Enter your question in the input box, click send or press Enter
2. **View System Information**: Click the "System Information" collapsible panel to view current configuration
3. **Clear History**: Click the "Clear History" button to clear chat records
4. **View Logs**: Check console output or `logs/agent.log` file

## 🚧 Current Limitations

- Only supports basic conversation functionality
- Tool calling and RAG functionality not yet implemented
- Telegram Bot not yet developed
- Only supports single-turn conversations (no context memory)

## 🔄 Future Plans

- [ ] M1 Phase: Implement tool calling system
- [ ] M2 Phase: Integrate RAG retrieval
- [ ] M3 Phase: Add multi-turn conversation memory
- [ ] M4 Phase: Implement Telegram Bot
- [ ] M5 Phase: Advanced features and optimizations

## 🤝 Contributing

Welcome to submit Issues and Pull Requests to improve this project!

## 📄 License

MIT License
