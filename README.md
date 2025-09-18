# 🤖 AgentFlow - Personal AI Assistant

**AgentFlow** is a personal AI assistant built on large language models, currently in M0 phase (runnable skeleton) with basic conversation capabilities.

**[中文说明](#中文说明)** | [English Description](#english-description)

## English Description

### ✨ Features

- **Multi-Model Support**: Seamlessly switch between Gemini and DeepSeek models
- **Unified Interface**: Consistent LLM calling interface with timeout and retry mechanisms
- **Comprehensive Logging**: INFO/DEBUG level logging with file and console output
- **Flexible Configuration**: Environment variables and .env file configuration
- **Modern UI**: Gradio-based chat interface
- **Modular Design**: Clean code structure for easy extension

### 🚀 Quick Start

#### 1. Environment Setup

```bash
# Clone or download the project
cd /path/to/AgentFlow

# Install dependencies
pip install -r requirements.txt
```

#### 2. Configure API Keys

Copy and edit the configuration file:

```bash
cp .env.example .env
```

Edit the `.env` file to set your API keys:

```env
# Choose the model provider
MODEL_PROVIDER=deepseek  # or gemini

# Set API keys (choose one or both)
GEMINI_API_KEY=your_gemini_api_key_here
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

#### 3. Launch the System

```bash
# Start Gradio interface
python main.py

# Or run UI directly
python ui_gradio.py
```

The system will start at `http://localhost:7860`, where you can access the chat interface in your browser.

### 📁 Project Structure

```
AgentFlow/
├── main.py                 # Main entry point
├── requirements.txt        # Dependencies
├── .env.example           # Configuration template
├── README.md              # Documentation
├── config.py              # Configuration management
├── logger.py              # Logging system
├── llm_interface.py       # LLM interface abstraction
├── agent_core.py          # Agent core logic
├── ui_gradio.py           # Gradio user interface
├── test_keys.py           # API key testing script
├── demo_models.py         # Model switching demo
├── rag_vector_store.py    # RAG retrieval (placeholder)
├── tool_registry.py       # Tool registry (placeholder)
├── tools/                 # Tool scripts directory
│   ├── tool_weather.py    # Weather tool (placeholder)
│   ├── tool_datetime.py   # DateTime tool (placeholder)
│   ├── tool_calculator.py # Calculator tool (placeholder)
│   ├── tool_calendar.py   # Calendar tool (placeholder)
│   ├── tool_email.py      # Email tool (placeholder)
│   ├── tool_websearch.py  # Web search tool (placeholder)
│   └── tool_file_reader.py # File reader tool (placeholder)
└── bot_telegram.py        # Telegram Bot (placeholder)
```

### ⚙️ Configuration

#### API Key Setup

**📍 Location: `.env` file in project root**

1. Copy the configuration file:
```bash
cp .env.example .env
```

2. Edit the `.env` file to set your API keys:

```env
# Choose model provider
MODEL_PROVIDER=deepseek  # or gemini

# Set API keys (choose one or both)
GEMINI_API_KEY=your_gemini_api_key_here
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

#### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_PROVIDER` | `gemini` | Model provider: `gemini` or `deepseek` |
| `GEMINI_API_KEY` | - | **Required**: Gemini API key |
| `DEEPSEEK_API_KEY` | - | **Required**: DeepSeek API key |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek API endpoint |
| `RAG_ENABLED` | `false` | Enable RAG functionality |
| `TOOLS_ENABLED` | `false` | Enable tool functionality |
| `LOG_LEVEL` | `INFO` | Log level: `INFO` or `DEBUG` |
| `MAX_TOKENS` | `4096` | Maximum tokens |
| `TEMPERATURE` | `0.7` | Generation temperature |
| `TIMEOUT_SECONDS` | `30` | Request timeout |
| `MAX_RETRIES` | `3` | Maximum retries |

#### 🔑 Get API Keys

- **Gemini API Key**:
  - Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
  - Create a new API key
  - **Note**: Free tier has strict quota limits, consider upgrading to paid tier

- **DeepSeek API Key**:
  - Visit [DeepSeek Platform](https://platform.deepseek.com/)
  - Register and create an API key
  - **Recommended**: DeepSeek offers very affordable pricing

#### ⚠️ API Quota Notes

- **Gemini Free Tier**: Strict rate limits and daily quotas
- **DeepSeek**: More generous free quotas, recommended for primary use
- Switch models in `.env` if you hit quota limits

### 🔧 Development

#### Independent Testing

The system supports independent testing in notebooks without full API key setup:

```python
# 1. Test configuration system
from config import get_config
config = get_config()
config.validate(require_api_keys=False)  # Skip API key validation

# 2. Test logging system
from logger import setup_logging, get_logger
setup_logging("DEBUG")
logger = get_logger()

# 3. Test LLM interface (requires API keys)
from llm_interface import create_llm_interface_with_keys
llm = create_llm_interface_with_keys()
result = await llm.generate("Hello, world!")

# 4. Test Agent core
from agent_core import AgentCore
agent = AgentCore()
agent.set_llm_interface(llm)
result = await agent.process("Hello")
```

#### Adding New LLM Providers

1. Inherit from `LLMProvider` class in `llm_interface.py`
2. Implement the `generate` method
3. Add the new provider in `LLMInterface._create_provider()`

#### Extending Agent Features

1. Add new logic in `agent_core.py`'s `process` method
2. Implement tool calling and RAG retrieval
3. Update configuration switches

#### Customizing UI

Modify the interface layout and styles in `ui_gradio.py`.

### 📝 Usage Instructions

1. **Basic Chat**: Type your message and press Enter or click Send
2. **System Info**: Click "System Info" panel to view current configuration
3. **Clear History**: Click "Clear History" to reset chat
4. **Log Viewing**: Check console output or `logs/agent.log` file

### 🚧 Current Limitations

- Basic conversation only
- Tool calling and RAG not yet implemented
- Telegram Bot not developed
- Single-turn conversations (no context memory)

### 🔄 Future Roadmap

- [ ] M1: Implement tool calling system
- [ ] M2: Integrate RAG retrieval
- [ ] M3: Add multi-turn conversation memory
- [ ] M4: Implement Telegram Bot
- [ ] M5: Advanced features and optimizations

---

## 中文说明

### ✨ 功能特性

- **多模型支持**: 支持Gemini和DeepSeek模型无缝切换
- **统一接口**: 统一的LLM调用接口，支持超时重试
- **完善日志**: INFO/DEBUG两档日志，支持文件和控制台输出
- **配置灵活**: 通过环境变量和.env文件进行配置
- **现代化UI**: 基于Gradio的聊天界面
- **模块化设计**: 清晰的代码结构，便于扩展

### 🚀 快速开始

#### 1. 环境准备

```bash
# 克隆或下载项目到本地
cd /path/to/AgentFlow

# 安装依赖
pip install -r requirements.txt
```

#### 2. 配置API密钥

复制并编辑配置文件：

```bash
cp .env.example .env
```

编辑`.env`文件，设置你的API密钥：

```env
# 选择使用的模型提供商
MODEL_PROVIDER=deepseek  # 或 gemini

# 设置API密钥（任选其一或全部设置）
GEMINI_API_KEY=你的Gemini_API密钥
DEEPSEEK_API_KEY=你的DeepSeek_API密钥
```

#### 3. 启动系统

```bash
# 启动Gradio界面
python main.py

# 或者直接运行UI
python ui_gradio.py
```

系统将在 `http://localhost:7860` 启动，你可以在浏览器中访问聊天界面。

### 🔑 获取API密钥

- **Gemini API密钥**:
  - 访问 [Google AI Studio](https://makersuite.google.com/app/apikey)
  - 创建新的API密钥
  - **注意**: 免费版有严格的配额限制，可能需要升级到付费版

- **DeepSeek API密钥**:
  - 访问 [DeepSeek平台](https://platform.deepseek.com/)
  - 注册账户并创建API密钥
  - **推荐**: DeepSeek提供非常便宜的接口价格

### ⚠️ API配额说明

- **Gemini免费版**: 有严格的请求频率和每日限制
- **DeepSeek**: 提供更充足的免费额度，推荐优先使用
- 如果遇到配额限制，可以在 `.env` 文件中切换 `MODEL_PROVIDER` 到另一个模型

### 🔧 开发说明

#### 独立测试各个功能点

系统设计支持在notebook中进行独立测试，无需完整的API密钥设置：

```python
# 1. 测试配置系统
from config import get_config
config = get_config()
config.validate(require_api_keys=False)  # 不验证API密钥

# 2. 测试日志系统
from logger import setup_logging, get_logger
setup_logging("DEBUG")
logger = get_logger()

# 3. 测试LLM接口（需要API密钥）
from llm_interface import create_llm_interface_with_keys
llm = create_llm_interface_with_keys()
await llm.generate("Hello, world!")

# 4. 测试Agent核心
from agent_core import AgentCore
agent = AgentCore()
agent.set_llm_interface(llm)
result = await agent.process("你好")
```

## 🤝 Contributing

Welcome to submit Issues and Pull Requests to improve this project!

## 📄 License

MIT License
