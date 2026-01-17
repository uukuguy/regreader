# 主智能体模式使用指南

## 概述

主智能体模式实现了**任务级编排 + 子智能体原子级执行**的 Bash+FS 范式：

- **主智能体**：任务级拆解（"定位章节"、"获取内容"），使用 Claude Agent SDK
- **子智能体**：原子级拆解和执行（"调用 get_toc()"），支持三框架封装
- **文件系统通信**：通过工作区文件进行任务分发和结果传递
- **完全可追踪**：所有执行过程记录到工作区

## 快速开始

### 1. 启动 MCP Server（SSE 模式）

```bash
regreader serve --transport sse --port 8080
```

### 2. 使用主智能体模式查询

```bash
regreader ask "锦苏直流系统发生闭锁故障时，安控装置的动作逻辑是什么？" \
  -r angui_2024 \
  --agent claude \
  -m \
  --mcp-transport sse \
  --mcp-url http://127.0.0.1:8080/sse
```

### 3. 查看执行记录

```bash
# 主智能体记录
cat coordinator/session_*/plan.md           # 任务拆解计划
cat coordinator/session_*/execution.md      # 执行过程记录
cat coordinator/session_*/final_report.md   # 最终答案

# 子智能体记录
cat subagents/search/task.md                # 收到的任务（任务级）
cat subagents/search/steps.md               # 原子任务执行记录
cat subagents/search/results.json           # 执行结果
```

## 架构说明

### 两层智能体体系

```
┌─────────────────────────────────────────────────────────┐
│  主智能体 (Claude Agent SDK + preset: "claude_code")     │
│  职责：任务级拆解、子任务调度、结果聚合                   │
│  工作区：coordinator/session_{id}/                      │
└─────────────────────────────────────────────────────────┘
                        ↓ 任务分发
        ┌───────────────┼───────────────┐
        ↓               ↓               ↓
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ SearchAgent  │ │  TableAgent  │ │ReferenceAgent│
│ (原子级执行)  │ │ (原子级执行)  │ │ (原子级执行)  │
└──────────────┘ └──────────────┘ └──────────────┘
        ↓               ↓               ↓
    MCP Tools:    MCP Tools:      MCP Tools:
    get_toc,      search_tables,  resolve_ref,
    smart_search  get_table       lookup_annotation
```

### 职责分离

| 智能体 | 职责 | 示例 |
|--------|------|------|
| **主智能体** | 任务级拆解 | "从规程目录中定位关于母线失压的章节" |
| **子智能体** | 原子级执行 | "调用 get_toc() → 解析结果 → 调用 smart_search()" |

### 工作区结构

**主智能体工作区**：
```
coordinator/session_20260116_210000/
├── plan.md          # 任务拆解计划
├── execution.md     # 子任务分发记录
└── final_report.md  # 最终答案
```

**子智能体工作区**：
```
subagents/search/
├── task.md          # 收到的任务（任务级）
├── steps.md         # 原子任务执行记录
└── results.json     # 执行结果
```

## CLI 参数说明

### 必需参数

- `query`: 查询问题（例如："锦苏直流安控装置在母线失压时的动作逻辑"）

### 常用选项

- `--reg-id`, `-r`: 限定规程（例如：`-r angui_2024`）
- `--agent`, `-a`: Agent 类型（`claude` | `pydantic` | `langgraph`）
- `--main-agent`, `-m`: 启用主智能体模式（任务级拆解 + Bash+FS 范式）

### MCP 相关选项

- `--mcp-transport`: MCP 传输方式（`stdio` | `sse`）
- `--mcp-url`: MCP Server URL（例如：`http://127.0.0.1:8080/sse`）

### 显示选项

- `--display`, `-d`: 显示模式（`simple` | `clean` | `enhanced`）
- `--verbose`, `-v`: 详细模式（显示完整工具参数和 DEBUG 日志）
- `--quiet`, `-q`: 静默模式（只显示最终结果）
- `--enhanced`, `-e`: 增强显示模式（历史记录 + 树状结构 + 进度条）

## 使用示例

### 示例 1：简单查询

```bash
regreader ask "母线失压如何处理?" -m -r angui_2024
```

### 示例 2：使用 SSE 模式连接远程 MCP Server

```bash
regreader ask "锦苏直流安控装置在母线失压时的动作逻辑" \
  -m \
  -r angui_2024 \
  --mcp-transport sse \
  --mcp-url http://127.0.0.1:8080/sse
```

### 示例 3：增强显示模式

```bash
regreader ask "表6-2注1的内容" \
  -m \
  -r angui_2024 \
  --display enhanced \
  --verbose
```

### 示例 4：JSON 输出

```bash
regreader ask "什么是安规?" -m --json
```

## 性能优化

### 会话复用

主智能体模式实现了 MCP 会话复用，避免重复加载嵌入模型：

**修复前**：
- 4 次调用 = 6.8 秒（每次加载模型 1.7 秒）

**修复后**：
- 4 次调用 = 2.0 秒（只加载一次模型）

### 验证会话复用

```bash
# 启动 MCP Server
regreader serve --transport sse --port 8080

# 运行测试
python tests/agents/test_mcp_session_reuse.py

# 预期输出
[MCP] 创建新会话: sse 模式  # 只创建一次
✓ 首次调用成功
✓ 第二次调用成功  # 复用会话
✓ 第三次调用成功  # 复用会话
✓ 第四次调用成功  # 复用会话
```

## 常见问题

### Q1: 如何查看主智能体如何拆解任务？

查看 `coordinator/session_{id}/plan.md`：

```bash
cat coordinator/session_*/plan.md
```

### Q2: 如何查看子智能体执行了哪些原子操作？

查看 `subagents/{type}/steps.md`：

```bash
cat subagents/search/steps.md
```

### Q3: 如何使用不同的 Agent 框架？

使用 `--agent` 参数：

```bash
# Claude SDK（默认）
regreader ask "..." -m --agent claude

# Pydantic AI
regreader ask "..." -m --agent pydantic

# LangGraph
regreader ask "..." -m --agent langgraph
```

### Q4: MCP Server 未启动怎么办？

启动 MCP Server：

```bash
# stdio 模式（默认）
regreader serve

# SSE 模式
regreader serve --transport sse --port 8080
```

### Q5: 如何使用多规程查询？

不指定 `--reg-id`，系统会自动识别：

```bash
regreader ask "什么是安全距离?" -m
```

## 技术细节

### 主智能体实现

- **文件**: `src/regreader/agents/main/agent.py`
- **框架**: Claude Agent SDK + `preset: "claude_code"`
- **方法**: `_decompose_task_with_llm()` - LLM 驱动的任务拆解
- **通信**: 通过文件系统（`task.md` / `results.json`）

### 子智能体实现

- **基类**: `src/regreader/subagents/bash_fs_base.py`
- **实现**: SearchAgent, TableAgent, ReferenceAgent
- **方法**: `decompose_task()` - 拆解为原子操作
- **方法**: `execute_atomic_step()` - 执行单个原子操作

### MCP 适配器

- **文件**: `src/regreader/mcp/adapter.py`
- **功能**: 会话复用、事件循环处理
- **传输**: stdio（本地子进程）或 sse（远程连接）

## 相关文档

- **详细设计**: `docs/dev/MCP_SESSION_REUSE_FIX.md`
- **工作日志**: `docs/dev/WORK_LOG.md`
- **测试**: `tests/agents/test_main_agent.py`
- **CLI 集成测试**: `tests/agents/test_cli_main_agent.py`

## 后续优化

1. **并行执行**: 支持多个子智能体并行执行独立任务
2. **上下文传递**: 子智能体之间通过文件系统传递上下文
3. **更多子智能体**: Exec-Subagent（脚本执行）、Validator-Subagent（结果验证）
4. **流式聚合**: 实时返回子智能体结果，而非等待全部完成
