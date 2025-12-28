# GridCode 项目设计方案

## 1. 项目定位

**GridCode** 是一个针对电力系统安规的智能检索与推理 Agent，模仿 Claude Code 的 Agentic Search 思路：
- 不进行复杂的预处理切片
- 以"页"为单位存储文档
- 利用 LLM 推理能力动态"翻书"、拼接、溯源

## 2. 核心架构（四层设计）

```
┌─────────────────────────────────────────────────────────────┐
│                    推理层 (Agentic Brain)                    │
│  ┌───────────────┬───────────────┬───────────────┐          │
│  │ Claude Agent  │  Pydantic AI  │   LangGraph   │          │
│  │    SDK        │  (多模型)     │   (多模型)    │          │
│  └───────────────┴───────────────┴───────────────┘          │
├─────────────────────────────────────────────────────────────┤
│                    工具层 (MCP Server)                       │
│     get_toc() | smart_search() | read_page_range()          │
├─────────────────────────────────────────────────────────────┤
│                    索引层 (Hybrid Index)                     │
│          SQLite FTS5 (关键词) + LanceDB (语义)               │
├─────────────────────────────────────────────────────────────┤
│                    存储层 (Page Store)                       │
│     Docling JSON (结构化) + Page-Level Markdown (阅读)       │
└─────────────────────────────────────────────────────────────┘
```

### 2.1 推理层三实现策略

| 实现 | 框架 | 支持模型 | 特点 |
|------|------|----------|------|
| **实现 A** | Claude Agent SDK | Claude (API/Bedrock/Vertex) | Claude 原生优化，MCP 原生支持 |
| **实现 B** | Pydantic AI | Claude/GPT/Qwen/本地模型 | 类型安全，与项目 Pydantic 模型一致 |
| **实现 C** | LangGraph | Claude/GPT/Qwen/本地模型 | 复杂工作流，状态管理 |

**设计原则**：三个实现共享同一套 MCP Server 工具层，仅推理层不同。

## 3. 数据模型设计

### 3.1 页面存储模型 (PageDocument)

```python
class PageDocument(BaseModel):
    """单页文档模型 - 一页可能包含多个内容块（文本、表格等）"""
    reg_id: str              # 规程标识 (如 "angui_2024")
    page_num: int            # 页码
    chapter_path: list[str]  # 章节路径 ["第六章", "事故处理", "母线故障"]

    # 内容块列表（一页可能有多个表格和文本段落）
    content_blocks: list[ContentBlock]  # 按阅读顺序排列的内容块

    # 页面级 Markdown（完整页面内容，供 LLM 阅读）
    content_markdown: str

    # 跨页标记
    continues_from_prev: bool  # 是否从上一页延续（如跨页表格）
    continues_to_next: bool    # 是否延续到下一页

    # 页面级注释
    annotations: list[Annotation]  # 页脚注释（注1、方案A等）
```

### 3.2 内容块模型 (ContentBlock)

```python
class ContentBlock(BaseModel):
    """页面内的内容块（文本或表格）"""
    block_id: str
    block_type: Literal["text", "table", "heading", "list"]

    # 位置信息
    order_in_page: int       # 在页面中的顺序

    # 内容
    content_markdown: str    # Markdown 格式内容

    # 表格专属字段（仅 block_type == "table" 时有效）
    table_meta: TableMeta | None = None
```

### 3.3 表格元数据 (TableMeta)

```python
class TableMeta(BaseModel):
    """表格元数据"""
    table_id: str
    caption: str | None      # 表格标题（如 "表6-2 母线故障处置"）
    is_truncated: bool       # 是否被截断（跨页）
    row_headers: list[str]   # 行标题
    col_headers: list[str]   # 列标题
    row_count: int           # 行数
    col_count: int           # 列数
    # 结构化数据（从 Docling JSON 提取）
    cells: list[TableCell]
```

### 3.4 注释模型 (Annotation)

```python
class Annotation(BaseModel):
    """页面注释"""
    annotation_id: str       # 如 "注1", "方案A"
    content: str             # 注释内容
    related_blocks: list[str]  # 关联的 block_id 列表
```

### 3.5 索引记录模型

```python
# SQLite FTS5 表结构
"""
CREATE VIRTUAL TABLE page_index USING fts5(
    content,                    -- 全文内容
    reg_id UNINDEXED,          -- 规程标识
    page_num UNINDEXED,        -- 页码
    chapter_path UNINDEXED     -- 章节路径（JSON 字符串）
);
"""
```

## 4. MCP Server 工具定义

### 4.1 get_toc (获取目录)

```json
{
  "name": "get_toc",
  "description": "获取安规的章节目录树及页码范围",
  "parameters": {
    "reg_id": {"type": "string", "description": "规程标识，如 angui_2024"}
  },
  "returns": "章节树结构，包含标题和页码范围"
}
```

### 4.2 smart_search (智能搜索)

```json
{
  "name": "smart_search",
  "description": "在安规中执行混合检索（关键词+语义）",
  "parameters": {
    "query": {"type": "string", "description": "搜索查询"},
    "reg_id": {"type": "string", "description": "规程标识"},
    "chapter_scope": {"type": "string", "description": "限定章节范围（可选）"},
    "limit": {"type": "integer", "default": 10}
  },
  "returns": "匹配片段列表，包含 page_num、chapter_path、snippet"
}
```

### 4.3 read_page_range (读取页面)

```json
{
  "name": "read_page_range",
  "description": "读取连续页面的完整 Markdown 内容",
  "parameters": {
    "reg_id": {"type": "string"},
    "start_page": {"type": "integer"},
    "end_page": {"type": "integer"}
  },
  "returns": "页面内容（自动处理跨页表格拼接）"
}
```

## 5. Agent 推理流程 (System Prompt 核心逻辑)

```
用户输入 "110kV 母线失压怎么处理？"
          │
          ▼
┌─────────────────────────────────────────┐
│ Phase 1: 目录路由                        │
│ 调用 get_toc() 锁定相关章节              │
│ 结果: "第六章 事故处理" (P40-P90)        │
└─────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────┐
│ Phase 2: 精准定位                        │
│ 调用 smart_search("母线失压",            │
│      chapter_scope="第六章")             │
│ 结果: P85 表6-2, P142 附录               │
└─────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────┐
│ Phase 3: 深度阅读                        │
│ 调用 read_page_range(85, 86)            │
│ - 检测表格是否跨页 → 自动拼接            │
│ - 识别"见注3" → 追踪注释内容             │
└─────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────┐
│ Phase 4: 结果生成                        │
│ 输出: 处置措施 + 来源引用                 │
│ [来源: 安规2024 P85 表6-2]              │
└─────────────────────────────────────────┘
```

## 6. 项目结构

```
grid-code/
├── pyproject.toml
├── src/
│   └── grid_code/
│       ├── __init__.py
│       ├── parser/                 # 解析层
│       │   ├── __init__.py
│       │   ├── docling_parser.py   # Docling 文档解析
│       │   └── page_extractor.py   # 页面级数据提取
│       ├── storage/                # 存储层
│       │   ├── __init__.py
│       │   ├── page_store.py       # 页面存储（JSON/Markdown）
│       │   └── models.py           # Pydantic 数据模型
│       ├── index/                  # 索引层
│       │   ├── __init__.py
│       │   ├── fts_index.py        # SQLite FTS5 关键词索引
│       │   └── vector_index.py     # LanceDB 语义索引
│       ├── mcp/                    # MCP Server (共享工具层)
│       │   ├── __init__.py
│       │   ├── server.py           # FastMCP 服务实现
│       │   └── tools.py            # 工具定义
│       ├── agents/                 # 推理层 (三实现)
│       │   ├── __init__.py
│       │   ├── base.py             # Agent 抽象基类
│       │   ├── claude_agent.py     # 实现 A: Claude Agent SDK
│       │   ├── pydantic_agent.py   # 实现 B: Pydantic AI
│       │   └── langgraph_agent.py  # 实现 C: LangGraph
│       ├── config.py               # 配置管理
│       └── cli.py                  # 命令行入口
├── tests/
│   └── main/
│       └── ...
└── docs/
    └── main/
        └── WORK_LOG.md
```

## 7. 技术栈

| 组件 | 技术选型 | 理由 |
|------|----------|------|
| 文档解析 | Docling | 表格结构识别强，保留 provenance (page_no) |
| 关键词索引 | SQLite FTS5 | 零部署成本，内置 Python |
| 语义索引 | LanceDB | 轻量级向量库，支持混合检索 |
| MCP Server | FastMCP | 官方推荐，易于集成 |
| 传输协议 | SSE / Streamable-HTTP | 作为独立服务部署 |
| Agent 框架 A | Claude Agent SDK | Claude 最佳体验，原生 MCP 支持 |
| Agent 框架 B | Pydantic AI | 类型安全，多模型支持，MCP 原生集成 |
| Agent 框架 C | LangGraph | 复杂工作流，状态管理 |
| 数据模型 | Pydantic | 类型安全，易于序列化 |
| CLI | Typer | 现代 Python CLI 框架 |

### Docling 支持的输入格式
- PDF, DOCX, PPTX, XLSX, HTML, Images

## 8. 实施阶段

### Phase 1: 基础设施 (Parser & Storage)
- [ ] 集成 Docling，实现 DOCX/PDF → JSON/Markdown 转换
- [ ] 构建数据模型（PageDocument, ContentBlock, TableMeta, Annotation）
- [ ] 实现页面级存储
- [ ] 验证 Docling 对安规表格的解析效果（一页多表场景）

### Phase 2: 索引层
- [ ] 构建 SQLite FTS5 全文索引
- [ ] 实现 LanceDB 语义索引
- [ ] 实现混合检索接口

### Phase 3: MCP Server
- [ ] 实现 get_toc 工具
- [ ] 实现 smart_search 工具
- [ ] 实现 read_page_range 工具（含跨页拼接逻辑）
- [ ] 实现 SSE 传输协议支持

### Phase 4: Agent 实现 A (Claude Agent SDK)
- [ ] 定义 Agent 抽象基类
- [ ] 集成 Claude Agent SDK
- [ ] 实现 MCP 工具调用
- [ ] 编写 System Prompt
- [ ] 端到端测试

### Phase 5: Agent 实现 B (Pydantic AI)
- [ ] 实现 Pydantic AI Agent
- [ ] 配置多模型支持（Claude/GPT/Qwen）
- [ ] 实现 MCP 工具调用
- [ ] 复用 System Prompt
- [ ] 对比测试

### Phase 6: Agent 实现 C (LangGraph)
- [ ] 实现 LangGraph Agent
- [ ] 配置多模型支持
- [ ] 实现 MCP 工具调用适配
- [ ] 复用 System Prompt
- [ ] 三框架对比测试

## 9. 关键设计决策

### 9.1 为什么选择 Page-Based 而非 Chunk-Based？
- 保持文档物理结构，便于引用定位
- 表格跨页可通过相邻页拼接处理
- 与 Claude Code 的文件级处理思路一致

### 9.2 为什么使用 JSON + Markdown 双格式？
- JSON：无损保留结构（表格坐标、provenance）
- Markdown：供 LLM 阅读，更自然的理解

### 9.3 跨页表格如何处理？
- Docling 提供 `is_truncated` 标记
- MCP Server 的 `read_page_range` 自动检测并拼接
- 拼接时保留表头信息

### 9.4 "见注1" 如何追踪？
- 解析时将页脚注释提取到 `annotations` 字段
- LLM 阅读时可直接看到注释内容
- 若需跨页注释，Agent 可主动调用工具搜索

## 10. 待确认事项

- [ ] 需要真实安规文档验证 Docling 解析效果
- [ ] 确认具体的注释格式（注1 vs 注① vs (注一)）
- [ ] 确认是否需要处理图片/公式（当前方案暂不处理）

---

## 11. CLI 工具设计

### 11.1 规程入库命令

```bash
# 转换并入库单个文件
gridcode ingest --file /path/to/angui_2024.docx --reg-id angui_2024

# 批量入库目录下所有文件
gridcode ingest --dir /path/to/regulations/ --format docx

# 查看已入库的规程
gridcode list
```

### 11.2 启动 MCP Server

```bash
# 启动 MCP Server (SSE 模式，用于独立服务)
gridcode serve --transport sse --port 8080

# 启动 MCP Server (stdio 模式，用于 Claude Desktop)
gridcode serve --transport stdio
```

### 11.3 测试检索

```bash
# 交互式测试
gridcode search "110kV 母线失压怎么处理"

# 指定规程
gridcode search --reg-id angui_2024 "变压器过热"
```

---

## 12. System Prompt 核心设计

```markdown
# Role
你是电力系统安规专家助理 GridCode，具备在安规文档中动态"翻书"的能力。

# 可用工具
1. get_toc(reg_id): 获取规程目录
2. smart_search(query, reg_id, chapter_scope?): 混合检索
3. read_page_range(reg_id, start_page, end_page): 读取页面

# 操作协议 (必须严格执行)

## 1. 目录优先原则
收到问题后，先调用 get_toc() 查看目录结构，锁定可能的章节范围。
严禁盲目全书搜索。

## 2. 表格完整性校验
当阅读表格时，检查以下标记：
- continues_to_next: true → 必须调用 read_page_range 读取下一页
- 表格单元格含"见注X" → 在当前页 annotations 中查找

## 3. 引用追踪
- 若内容是缩写（如"方案甲"），必须追踪到完整定义
- 若引用其他条款（如"见第X条"），必须调用工具查找

## 4. 输出格式
所有回答必须包含：
- 【来源】: 规程名 + 页码 + 表格/章节编号
- 【处置措施】: 具体步骤（编号列表）
- 【注意事项】: 相关备注和限制条件

## 5. 拒绝策略
- 如果是闲聊或与安规无关的问题，礼貌拒绝
- 如果找不到相关规定，明确说明"未找到相关规定"
```

---

## 13. 核心代码模块职责

| 模块 | 文件 | 职责 |
|------|------|------|
| 文档解析 | `parser/docling_parser.py` | Docling 封装，PDF/DOCX → JSON |
| 页面提取 | `parser/page_extractor.py` | 从 DoclingDocument 提取页面数据 |
| 数据模型 | `storage/models.py` | PageDocument, ContentBlock, TableMeta 等 |
| 页面存储 | `storage/page_store.py` | 页面的持久化和读取 |
| 关键词索引 | `index/fts_index.py` | SQLite FTS5 封装 |
| 语义索引 | `index/vector_index.py` | LanceDB 封装 |
| MCP 工具 | `mcp/tools.py` | get_toc, smart_search, read_page_range |
| MCP 服务 | `mcp/server.py` | FastMCP 服务入口 |
| Agent 基类 | `agents/base.py` | Agent 抽象接口 |
| Claude Agent | `agents/claude_agent.py` | Claude Agent SDK 实现 |
| Pydantic Agent | `agents/pydantic_agent.py` | Pydantic AI 实现 |
| LangGraph Agent | `agents/langgraph_agent.py` | LangGraph 实现 |
| CLI | `cli.py` | 命令行入口 (typer) |

---

## 14. 三框架对比预期

| 维度 | Claude Agent SDK | Pydantic AI | LangGraph |
|------|------------------|-------------|-----------|
| 推理能力 | Claude 原生优化 | 依赖选用的 LLM | 依赖选用的 LLM |
| MCP 集成 | 原生支持 | 原生支持 | 需要适配层 |
| 模型灵活性 | 仅 Claude | Claude/GPT/Qwen/本地模型 | Claude/GPT/Qwen/本地模型 |
| 类型安全 | 一般 | 强（Pydantic 原生） | 一般 |
| 工作流控制 | 简单 | 中等 | 复杂工作流支持 |
| 部署复杂度 | 简单 | 简单 | 中等 |
| 企业适用性 | 需 Claude API | 灵活可选 | 灵活可选 |
| 学习曲线 | 低 | 低 | 中等 |
