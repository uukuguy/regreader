# 主智能体模式使用示例

## 概述

主智能体模式实现了两层架构：
- **主智能体**（MainAgent）：任务级拆解
- **子智能体**（Subagents）：原子级执行

## 快速开始

### 1. 启动 MCP Server

```bash
# SSE 模式（推荐）
regreader serve --transport sse --port 8080

# stdio 模式
regreader serve --transport stdio
```

### 2. 使用主智能体模式查询

```bash
# 基本用法
regreader ask "锦苏直流系统发生闭锁故障时，安控装置的动作逻辑是什么？" \
  -r angui_2024 \
  --agent claude \
  -m

# 带增强显示
regreader ask "锦苏直流安控装置在母线失压时的动作逻辑" \
  -r angui_2024 \
  --agent claude \
  --display enhanced \
  -m

# 使用 Makefile
make ask AGENT=claude REG=angui_2024 AGENT_FLAGS="-m" \
  ASK_QUERY="锦苏直流系统发生闭锁故障时，安控装置的动作逻辑是什么？"
```

### 3. 查看执行记录

```bash
# 主智能体记录
cat coordinator/session_*/plan.md          # 任务拆解计划
cat coordinator/session_*/execution.md     # 执行过程
cat coordinator/session_*/final_report.md  # 最终答案

# 子智能体记录
cat subagents/search/task.md      # 收到的任务
cat subagents/search/steps.md     # 原子任务执行过程
cat subagents/search/results.json # 执行结果
```

## 架构说明

### 主智能体职责

**输入**：用户查询
```bash
"锦苏直流系统发生闭锁故障时，安控装置的动作逻辑是什么？"
```

**输出**：任务级子任务
```json
[
  {
    "task_type": "search",
    "description": "从规程目录中定位关于闭锁故障的章节"
  },
  {
    "task_type": "search",
    "description": "从指定章节范围获得与安控装置动作逻辑相关的内容"
  }
]
```

**记录**：
- `coordinator/session_{id}/plan.md` - 任务拆解计划
- `coordinator/session_{id}/execution.md` - 子任务分发记录
- `coordinator/session_{id}/final_report.md` - 最终答案

### 子智能体职责

**输入**：任务级描述
```markdown
# 搜索任务

## 任务描述
从规程目录中定位关于闭锁故障的章节

## 上下文
- 规程 ID: angui_2024
- 会话 ID: 20260116_123456
```

**输出**：原子操作序列
```json
[
  {
    "step": 1,
    "description": "获取规程目录结构",
    "action": "get_toc",
    "params": {"reg_id": "angui_2024"}
  },
  {
    "step": 2,
    "description": "搜索闭锁故障相关内容",
    "action": "smart_search",
    "params": {
      "query": "闭锁故障",
      "reg_id": "angui_2024"
    }
  }
]
```

**记录**：
- `subagents/{type}/task.md` - 收到的任务
- `subagents/{type}/steps.md` - 原子任务执行过程
- `subagents/{type}/results.json` - 执行结果

## 子智能体类型

### SearchAgent（文档搜索）
- **职责**：文档搜索和内容提取
- **工具**：get_toc, smart_search, read_page_range
- **工作区**：`subagents/search/`

### TableAgent（表格操作）
- **职责**：表格查找和数据提取
- **工具**：search_tables, get_table_by_id
- **工作区**：`subagents/table/`

### ReferenceAgent（引用解析）
- **职责**：交叉引用解析
- **工具**：resolve_reference, lookup_annotation
- **工作区**：`subagents/reference/`

## 配置选项

### 环境变量

```bash
# MCP 配置
export REGREADER_MCP_TRANSPORT=sse  # or stdio
export REGREADER_MCP_HOST=127.0.0.1
export REGREADER_MCP_PORT=8080

# LLM 配置
export REGREADER_LLM_MODEL_NAME=claude-sonnet-4-20250514
export REGREADER_LLM_API_KEY=your-api-key
```

### CLI 选项

```bash
regreader ask [QUERY] \
  -r, --reg_id TEXT          # 规程 ID
  --agent [claude|pydantic|langgraph]  # 使用的框架
  -m, --main-agent           # 启用主智能体模式
  --display [simple|enhanced|verbose]  # 显示模式
```

## 示例会话

```bash
# 1. 启动 MCP Server
regreader serve --transport sse --port 8080

# 2. 在另一个终端运行查询
regreader ask "锦苏直流系统发生闭锁故障时，安控装置的动作逻辑是什么？稳规对此类故障下的系统稳定有什么要求？" \
  -r angui_2024 \
  --agent claude \
  --display enhanced \
  -m

# 3. 查看执行记录
echo "=== 主智能体任务计划 ==="
cat coordinator/session_*/plan.md

echo "=== 主智能体执行日志 ==="
cat coordinator/session_*/execution.md

echo "=== 搜索子智能体执行步骤 ==="
cat subagents/search/steps.md

echo "=== 搜索子智能体结果 ==="
cat subagents/search/results.json | jq
```

## 故障排除

### 问题 1：MCP 连接失败

**错误**：
```
Error: Cannot connect to MCP server
```

**解决**：
```bash
# 检查 MCP Server 是否运行
ps aux | grep regreader

# 检查端口是否占用
lsof -i :8080

# 重启 MCP Server
regreader serve --transport sse --port 8080
```

### 问题 2：LLM 调用失败

**错误**：
```
LLM 拆解失败，回退到规则拆解
```

**解决**：
```bash
# 检查 API Key
echo $REGREADER_LLM_API_KEY

# 检查模型名称
echo $REGREADER_LLM_MODEL_NAME

# 测试连接
regreader ask "测试查询" -r angui_2024 --agent claude
```

### 问题 3：子智能体任务文件不存在

**错误**：
```
FileNotFoundError: 任务文件不存在
```

**解决**：
```bash
# 检查工作区结构
ls -la subagents/search/

# 手动创建任务文件（测试用）
echo "# 测试任务" > subagents/search/task.md
```

## 性能优化

### 1. 使用 SSE 模式

SSE 模式比 stdio 模式更快，因为可以保持长连接：

```bash
# 推荐
regreader serve --transport sse --port 8080
regreader ask "..." --mcp-transport sse --mcp-url http://127.0.0.1:8080/sse

# 不推荐（每次查询都启动新进程）
regreader serve --transport stdio
```

### 2. 启用嵌入模型缓存

嵌入模型加载后会缓存到 `~/.cache/torch/sentence_transformers/`：

```bash
# 第一次运行会下载模型（较慢）
# 后续运行会使用缓存（快速）
```

### 3. 并行执行（未来版本）

当前版本按顺序执行子任务，未来版本支持并行：

```python
# 未来版本示例
tasks = [
    {"task_type": "search", "description": "定位章节 A"},
    {"task_type": "search", "description": "定位章节 B"},
    {"task_type": "table", "description": "查找表格"},
]
# 三个子任务可以并行执行
```

## 最佳实践

### 1. 复杂查询使用主智能体模式

```bash
# 简单查询（单智能体更快）
regreader ask "什么是安规？" -r angui_2024

# 复杂查询（主智能体模式更好）
regreader ask "锦苏直流系统发生闭锁故障时，安控装置的动作逻辑是什么？稳规对此类故障下的系统稳定有什么要求？" \
  -r angui_2024 -m
```

### 2. 查看执行记录了解推理过程

```bash
# 查看主智能体如何拆解任务
cat coordinator/session_*/plan.md

# 查看子智能体如何执行原子操作
cat subagents/search/steps.md
```

### 3. 根据需求选择框架

```bash
# Claude SDK（推荐，官方最佳实践）
regreader ask "..." --agent claude -m

# Pydantic AI（类型安全）
regreader ask "..." --agent pydantic -m

# LangGraph（状态管理）
regreader ask "..." --agent langgraph -m
```

## 相关文档

- [Bash+FS 架构设计](../bash-fs-paradiam/ARCHITECTURE_DESIGN.md)
- [子智能体架构](../subagents/SUBAGENTS_ARCHITECTURE.md)
- [MCP 工具设计](MCP_TOOLS_DESIGN.md)
- [开发工作日志](WORK_LOG.md)
