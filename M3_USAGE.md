# M3 双模型推理管线使用指南

## 🚀 概述

M3（Multi-Model Orchestrator）是一个先进的双模型推理管线，实现了完整的PLAN→ACT→JUDGE状态机，支持复杂的多步骤任务执行。

## 🏗️ 架构特点

- **双模型分工**：
  - **Planner (DeepSeek-R1)**: 负责推理规划和制定执行计划
  - **Executor (DeepSeek-V3/V3.1)**: 负责执行工具调用和具体操作
  - **Judge (DeepSeek-R1)**: 负责评估执行结果和决定下一步

- **智能状态机**：
  - PLAN: 生成执行计划
  - ACT: 执行计划步骤
  - JUDGE: 评估结果并决定是否继续或完成

## 📋 使用方法

### 1. 传统模式（默认）
```python
from agent_core import create_agent_core_with_llm

# 使用传统Agent模式
agent = create_agent_core_with_llm(use_m3=False)
result = await agent.process("现在几点了？")
print(result['response'])
```

### 2. M3 编排器模式
```python
from agent_core import create_agent_core_with_llm

# 启用M3编排器模式
agent = create_agent_core_with_llm(use_m3=True)
result = await agent.process("帮我计算一下复杂的数学题，然后查询天气")

# 查看详细的编排信息
print(f"编排状态: {result['metadata']['mode']}")
print(f"迭代次数: {result['metadata']['iteration_count']}")
print(f"工具调用轨迹: {len(result['metadata']['tool_call_trace'])}")
```

### 3. 环境变量控制
```bash
# 启用M3模式
export USE_M3_ORCHESTRATOR=true

# 然后启动Gradio UI
python ui_gradio.py
```

### 4. 直接使用编排器
```python
from orchestrator import orchestrate_query

# 直接使用编排器
result = await orchestrate_query("分析这份文档并生成摘要")
print(f"最终答案: {result.final_answer}")
print(f"执行步骤: {len(result.final_plan.steps)}")
```

## 🔧 配置选项

### 编排器参数
```python
from orchestrator import Orchestrator

# 自定义编排器配置
orchestrator = Orchestrator(
    max_iterations=3,      # 最大迭代次数
    max_execution_time=60  # 最大执行时间（秒）
)
```

### 模型选择
- **Planner/Judge**: 自动使用 `deepseek-reasoner`（推理增强）
- **Executor**: 自动使用 `deepseek-chat`（工具调用优化）

## 📊 功能特性

### ✅ 已实现功能
- [x] 完整的PLAN→ACT→JUDGE状态机
- [x] 自动工具调用和结果处理
- [x] 智能迭代和错误重试
- [x] JSON格式严格验证
- [x] 详细的执行日志记录

### 🔄 工作流程示例

```
用户查询: "帮我计算(12+3*4)^2，然后告诉我北京的天气"

1. PLAN阶段 (DeepSeek-R1)
   ├── 分析查询需求
   ├── 生成执行计划:
   │   ├── 步骤1: 调用math_calc工具计算数学题
   │   └── 步骤2: 调用weather_get工具查询天气
   └── 输出JSON格式的计划

2. ACT阶段 (DeepSeek-V3)
   ├── 执行步骤1: math_calc("(12+3*4)^2")
   ├── 保存结果: {"result": 225}
   ├── 执行步骤2: weather_get({"location": "北京"})
   └── 保存结果: {"weather": "晴天", "temperature": "25°C"}

3. JUDGE阶段 (DeepSeek-R1)
   ├── 评估执行结果
   ├── 判断是否满足用户需求
   └── 输出满意度分析

4. 最终输出
   ├── 数学计算结果: 225
   └── 北京天气: 晴天, 25°C
```

## 🛠️ 可用工具

| 工具名称 | 功能描述 | 参数示例 |
|---------|---------|---------|
| `time_now` | 获取当前时间 | `{}` |
| `math_calc` | 数学计算 | `{"expression": "(12+3*4)^2"}` |
| `weather_get` | 天气查询 | `{"location": "北京"}` |
| `calendar_read` | 日程查看 | `{"start_date": "2025-01-01"}` |
| `email_list` | 邮件查看 | `{"limit": 10}` |
| `file_read` | 文件读取 | `{"file_path": "document.txt"}` |

## 📈 性能监控

### 状态指标
```python
result = await agent.process("查询任务")

# 查看编排器状态
metadata = result['metadata']
print(f"模式: {metadata['mode']}")
print(f"状态: {metadata['status']}")
print(f"迭代次数: {metadata['iteration_count']}")
print(f"总时间: {metadata['total_time']:.2f}s")
print(f"工具调用: {len(metadata['tool_call_trace'])}")
```

### 日志记录
所有编排过程都会记录详细日志：
- `/logs/agent.log` - 主要日志
- 控制台输出 - 实时状态

## ⚠️ 注意事项

1. **资源消耗**: M3模式会消耗更多API调用，可能产生更高费用
2. **响应时间**: 复杂任务可能需要更长时间完成
3. **错误处理**: 系统会自动重试失败的操作，但可能需要手动干预
4. **数据验证**: 所有输入输出都会进行严格验证

## 🔧 故障排除

### 常见问题
1. **"LLM调用失败"** - 检查API密钥和网络连接
2. **"工具不存在"** - 确认工具名称拼写正确
3. **"迭代次数超限"** - 任务可能过于复杂，尝试简化
4. **"执行超时"** - 增加max_execution_time参数

### 调试模式
```python
import logging
logging.getLogger().setLevel(logging.DEBUG)
```

## 🎯 最佳实践

1. **选择合适的模式**:
   - 简单查询用传统模式
   - 复杂多步骤任务用M3模式

2. **合理设置参数**:
   - 根据任务复杂度调整max_iterations
   - 预估执行时间设置max_execution_time

3. **监控资源使用**:
   - 定期检查API调用次数和费用
   - 监控响应时间和成功率

## 📚 技术细节

- **状态机实现**: 基于异步协程的状态转换
- **错误处理**: 多层异常捕获和自动重试
- **数据流**: 结构化的artifact管理和传递
- **扩展性**: 插件式的工具和模块设计

---

**如有问题，请查看日志文件或联系技术支持。**
