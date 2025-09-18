# AgentFlow 个人助手

这是 AgentFlow 个人助手的示例文档，用于测试 RAG 功能。

## 主要功能

- **真·流式响应**: 支持实时流式输出
- **事件分流**: 状态信息显示在侧栏
- **AskUser 续跑**: 会话状态自动管理
- **本地 RAG**: 基于 Chroma 的文档检索

## 使用方法

1. 启动 Chainlit UI：
   ```bash
   chainlit run ui_chainlit.py -w
   ```

2. 在浏览器中访问 http://localhost:7860

3. 发送消息测试各项功能

## 注意事项

- 文件写入仅限桌面目录
- API 密钥需要正确配置
- 文档摄入支持 .md、.txt、.pdf 格式
