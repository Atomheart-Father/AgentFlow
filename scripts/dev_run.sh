#!/bin/bash

# AgentFlow 本地开发启动脚本
# 使用单worker确保session粘性，避免WS连接切断问题

echo "🚀 启动AgentFlow本地开发服务器..."
echo "📝 配置说明:"
echo "  - 单worker模式: 确保session粘性"
echo "  - WebSocket透传: 支持实时流式响应"
echo "  - Session管理: 支持AskUser续跑"
echo ""

# 设置环境变量
export CHAINLIT_HOST=0.0.0.0
export CHAINLIT_PORT=8000

# 单worker启动
echo "🔧 使用单worker模式启动..."
chainlit run ui_chainlit.py --workers 1 --host 0.0.0.0 --port 8000

echo ""
echo "✅ 服务器已停止"
