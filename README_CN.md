# GridCode

**电力规程智能检索 Agent**

[English](README.md)

GridCode 是一个面向电力系统安全规程（安规）的智能检索与推理 Agent。不同于传统 RAG 的切片策略，GridCode 采用 **基于页面的 Agentic Search** 方法——让 LLM 像人类专家一样动态"翻书"、拼接跨页表格、追踪引用注释。

## 为什么需要 GridCode？

电力规程文档具有传统 RAG 难以处理的特殊挑战：

| 挑战 | 传统 RAG | GridCode |
|------|----------|----------|
| **复杂表格** | 切片破坏表格结构 | 页面级存储保持表格完整 |
| **跨页表格** | 切片边界丢失上下文 | Agent 检测截断标记，主动获取下一页 |
| **行内引用** ("见注1") | 遗漏或孤立 | Agent 在页面上下文中追踪注释 |
| **来源归属** | 近似的切片位置 | 精确页码 + 表格编号 |

## 设计思路

受 Claude Code 搜索代码库方式的启发，GridCode 将规程文档视为"可翻阅的书籍"而非"待匹配的向量"：

```
┌─────────────────────────────────────────────────────────────┐
│                      推理层 (Reasoning)                      │
│       Claude Agent SDK  |  Pydantic AI  |  LangGraph        │
├─────────────────────────────────────────────────────────────┤
│                      工具层 (MCP Server)                     │
│        get_toc()  |  smart_search()  |  read_page_range()   │
├─────────────────────────────────────────────────────────────┤
│                      索引层 (可插拔架构)                      │
│  关键词: FTS5 / Tantivy / Whoosh                             │
│  向量:   LanceDB / Qdrant                                    │
├─────────────────────────────────────────────────────────────┤
│                      存储层 (Storage)                        │
│           Docling JSON (结构化) + Markdown (阅读)            │
└─────────────────────────────────────────────────────────────┘
```

### 核心原则

1. **以页为单位**：按物理页面存储文档，而非任意切片。保持文档结构，支持精确引用。

2. **混合检索**：结合 FTS5 关键词搜索（设备名称、故障代码）与向量搜索（故障现象描述）。

3. **Agentic 推理**：由 LLM 决定何时获取更多上下文——读取相邻页面处理跨页表格、追踪"见注3"引用、深入附录查找详情。

4. **多框架实现**：三种 Agent 实现共享同一套 MCP 工具：
   - **Claude Agent SDK**：Claude 模型最优体验，原生 MCP 支持
   - **Pydantic AI**：类型安全，模型无关，生产就绪
   - **LangGraph**：复杂工作流编排

5. **统一 MCP 访问**：所有 Agent 通过 MCP 协议访问页面数据——PageStore 由 MCP Server 内部控制，确保一致的数据访问模式。

## 数据模型

每页存储为 `PageDocument`，包含有序的 `ContentBlock`（文本、表格、标题）。支持常见的一页多表场景：

```python
PageDocument
├── reg_id: "angui_2024"
├── page_num: 85
├── chapter_path: ["第六章", "事故处理", "母线故障"]
├── content_blocks: [
│   ├── ContentBlock(type="heading", content="6.2 母线故障处置")
│   ├── ContentBlock(type="table", table_meta=TableMeta(...))
│   └── ContentBlock(type="table", table_meta=TableMeta(...))  # 支持多表
│   ]
├── continues_to_next: true  # 表格被截断，延续至 P86
└── annotations: [Annotation(id="注1", content="...")]
```

## MCP 工具

| 工具 | 用途 |
|------|------|
| `get_toc(reg_id)` | 返回章节目录树及页码范围——Agent 用此缩小搜索范围 |
| `smart_search(query, reg_id, chapter_scope?)` | 混合检索，返回带页码的匹配片段 |
| `read_page_range(reg_id, start, end)` | 获取页面完整 Markdown，自动拼接跨页表格 |

## Agent 推理流程

```
用户: "110kV 母线失压怎么处理？"
                    │
                    ▼
    ┌───────────────────────────────────┐
    │ 1. 目录路由                        │
    │    get_toc() → 第六章 (P40-90)     │
    └───────────────────────────────────┘
                    │
                    ▼
    ┌───────────────────────────────────┐
    │ 2. 精准定位                        │
    │    smart_search("母线失压",        │
    │         chapter="第六章")          │
    │    → P85 表6-2                    │
    └───────────────────────────────────┘
                    │
                    ▼
    ┌───────────────────────────────────┐
    │ 3. 深度阅读                        │
    │    read_page_range(85, 86)        │
    │    - 检测表格延续 → 自动拼接       │
    │    - 发现"见注3" → 解析注释        │
    └───────────────────────────────────┘
                    │
                    ▼
    ┌───────────────────────────────────┐
    │ 4. 生成带引用的回答                 │
    │    [来源: 安规2024 P85 表6-2]      │
    └───────────────────────────────────┘
```

## 技术栈

| 组件 | 选型 | 理由 |
|------|------|------|
| 文档解析 | Docling | 表格结构识别，provenance (page_no) 追踪 |
| 关键词索引 | SQLite FTS5 (默认) | 零部署成本，Python 内置 |
| 关键词索引 | Tantivy (可选) | 高性能 Rust 引擎 |
| 关键词索引 | Whoosh (可选) | 纯 Python，支持中文分词 |
| 向量索引 | LanceDB (默认) | 轻量级，支持混合检索 |
| 向量索引 | Qdrant (可选) | 生产级，支持分布式 |
| MCP Server | FastMCP | 官方 SDK，SSE 传输 |
| Agent 框架 | Claude SDK / Pydantic AI / LangGraph | 适应不同部署场景 |

## 安装

```bash
# 基础安装
pip install grid-code

# 安装可选索引后端
pip install grid-code[tantivy]     # 高性能关键词搜索
pip install grid-code[whoosh]      # 中文分词支持
pip install grid-code[qdrant]      # 生产级向量数据库

# 安装所有索引后端
pip install grid-code[all-indexes]
```

## 配置

通过环境变量配置索引后端：

```bash
# 选择关键词索引后端 (fts5/tantivy/whoosh)
export GRIDCODE_KEYWORD_INDEX_BACKEND=fts5

# 选择向量索引后端 (lancedb/qdrant)
export GRIDCODE_VECTOR_INDEX_BACKEND=lancedb

# Qdrant 服务器配置 (使用 qdrant 时)
export GRIDCODE_QDRANT_URL=http://localhost:6333
```

## Agent 使用

GridCode 提供三种 Agent 实现，每个 Agent 都通过 MCP 协议与 MCP Server 通信：

### Claude Agent SDK（推荐用于 Claude 模型）

使用官方 Claude Agent SDK，原生支持 MCP：

```bash
# 设置 API Key
export GRIDCODE_ANTHROPIC_API_KEY="your-api-key"

# 启动 Claude Agent 对话
gridcode chat --agent claude --reg-id angui_2024
```

### Pydantic AI Agent（多模型支持）

类型安全的 Agent，支持多种 LLM 提供商：

```bash
# Anthropic 模型
export GRIDCODE_ANTHROPIC_API_KEY="your-api-key"

# OpenAI 模型
export GRIDCODE_OPENAI_API_KEY="your-api-key"

# 启动对话
gridcode chat --agent pydantic --reg-id angui_2024
```

### LangGraph Agent（复杂工作流）

用于高级工作流编排：

```bash
export GRIDCODE_ANTHROPIC_API_KEY="your-api-key"

gridcode chat --agent langgraph --reg-id angui_2024
```

### 架构说明

所有 Agent 通过 MCP 协议访问页面数据：

```
┌─────────────────────────────────────────────────┐
│                  Agent 层                        │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────┐ │
│  │ ClaudeAgent │  │ LangGraph   │  │ Pydantic │ │
│  │ (SDK MCP)   │  │ Agent       │  │ AI Agent │ │
│  └──────┬──────┘  └──────┬──────┘  └────┬─────┘ │
│         │                │               │       │
│         │         ┌──────┴───────────────┘       │
│         │         │                              │
│         │         ▼                              │
│         │  GridCodeMCPClient                     │
└─────────┼─────────┬──────────────────────────────┘
          │         │
          │  stdio  │  stdio
          ▼         ▼
┌─────────────────────────────────────────────────┐
│            GridCode MCP Server                   │
│   get_toc | smart_search | read_page_range      │
└─────────────────────────────────────────────────┘
```

## 项目状态

核心实现已完成。剩余工作：

- [x] Phase 1: Docling 集成，页面级存储
- [x] Phase 2: FTS5 + LanceDB 索引（可插拔后端架构）
- [x] Phase 3: MCP Server（SSE 传输）
- [x] Phase 4-6: 三种 Agent 实现
- [ ] 使用真实规程文档进行端到端测试
- [ ] 各索引后端性能对比测试

## 开源协议

MIT
