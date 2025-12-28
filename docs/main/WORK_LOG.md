# GridCode 工作日志

## 2025-12-28 核心架构实现完成

### 会话概述
完成 GridCode 项目核心架构的代码实现，按设计方案 6 个阶段全部完成。

### 实现内容

#### Phase 1: 基础设施 (Parser & Storage)

**创建的文件：**
- `src/grid_code/__init__.py` - 包初始化
- `src/grid_code/exceptions.py` - 自定义异常类
- `src/grid_code/config.py` - 配置管理（使用 Pydantic Settings）
- `src/grid_code/storage/models.py` - 核心数据模型
  - `TableCell`, `TableMeta` - 表格结构
  - `Annotation` - 页面注释
  - `ContentBlock` - 内容块
  - `PageDocument` - 页面文档（核心存储单位）
  - `TocItem`, `TocTree` - 目录结构
  - `SearchResult`, `PageContent` - 检索结果
  - `RegulationInfo` - 规程信息
- `src/grid_code/parser/docling_parser.py` - Docling 文档解析器封装
- `src/grid_code/parser/page_extractor.py` - 页面级数据提取器
- `src/grid_code/storage/page_store.py` - 页面存储管理器

#### Phase 2: 索引层

**创建的文件：**
- `src/grid_code/index/fts_index.py` - SQLite FTS5 全文索引
  - 支持 BM25 排名
  - 支持章节范围过滤
- `src/grid_code/index/vector_index.py` - LanceDB 语义向量索引
  - 使用 sentence-transformers 生成嵌入
  - 默认模型: BAAI/bge-small-zh-v1.5
- `src/grid_code/index/hybrid_search.py` - 混合检索接口
  - RRF (Reciprocal Rank Fusion) 算法融合结果
  - 可配置权重比例

#### Phase 3: MCP Server

**创建的文件：**
- `src/grid_code/mcp/tools.py` - 工具定义
  - `get_toc()` - 获取规程目录
  - `smart_search()` - 混合检索
  - `read_page_range()` - 读取页面（含跨页表格拼接）
  - `list_regulations()` - 列出规程
- `src/grid_code/mcp/server.py` - FastMCP 服务实现
  - 支持 SSE 和 stdio 传输协议

#### Phase 4: Claude Agent SDK 实现

**创建的文件：**
- `src/grid_code/agents/base.py` - Agent 抽象基类
- `src/grid_code/agents/prompts.py` - System Prompt 定义
- `src/grid_code/agents/claude_agent.py` - Claude Agent SDK 实现

#### Phase 5: Pydantic AI Agent 实现

**创建的文件：**
- `src/grid_code/agents/pydantic_agent.py` - Pydantic AI 实现
  - 支持多模型切换（Anthropic/OpenAI）

#### Phase 6: LangGraph Agent 实现

**创建的文件：**
- `src/grid_code/agents/langgraph_agent.py` - LangGraph 实现
  - 使用状态图管理对话流程
  - 支持复杂工作流

#### CLI 实现

**创建的文件：**
- `src/grid_code/cli.py` - Typer CLI 入口
  - `gridcode ingest` - 入库文档
  - `gridcode serve` - 启动 MCP Server
  - `gridcode list` - 列出规程
  - `gridcode search` - 测试检索
  - `gridcode chat` - 交互对话
  - `gridcode delete` - 删除规程
  - `gridcode version` - 版本信息

### 项目结构

```
src/grid_code/
├── __init__.py
├── cli.py
├── config.py
├── exceptions.py
├── parser/
│   ├── __init__.py
│   ├── docling_parser.py
│   └── page_extractor.py
├── storage/
│   ├── __init__.py
│   ├── models.py
│   └── page_store.py
├── index/
│   ├── __init__.py
│   ├── fts_index.py
│   ├── vector_index.py
│   └── hybrid_search.py
├── mcp/
│   ├── __init__.py
│   ├── tools.py
│   └── server.py
└── agents/
    ├── __init__.py
    ├── base.py
    ├── prompts.py
    ├── claude_agent.py
    ├── pydantic_agent.py
    └── langgraph_agent.py
```

### 使用说明

```bash
# 安装依赖
uv sync

# 入库文档
gridcode ingest --file /path/to/angui.docx --reg-id angui_2024

# 启动 MCP Server
gridcode serve --transport sse --port 8080

# 测试检索
gridcode search "母线失压" --reg-id angui_2024

# 交互对话
gridcode chat --reg-id angui_2024 --agent claude
```

### 配置说明

可通过环境变量配置：

```bash
# API Keys
export GRIDCODE_ANTHROPIC_API_KEY="sk-..."
export GRIDCODE_OPENAI_API_KEY="sk-..."

# 数据目录
export GRIDCODE_DATA_DIR="./data"

# 检索权重
export GRIDCODE_FTS_WEIGHT=0.4
export GRIDCODE_VECTOR_WEIGHT=0.6
```

### 待完成事项

1. **测试验证**
   - 需要真实安规文档验证 Docling 解析效果
   - 编写单元测试和集成测试
   - 验证跨页表格拼接逻辑

2. **功能增强**
   - 支持更多注释格式（注①、方案甲等）
   - 添加图片/公式处理（如有需要）
   - 完善错误处理和日志

3. **性能优化**
   - 批量入库优化
   - 向量检索调优
   - 缓存机制

---

## 2025-12-28 设计阶段完成

### 会话概述
完成 GridCode 项目的整体设计方案，包括架构设计、数据模型、MCP 工具定义和实施计划。

### 主要成果

1. **架构设计**
   - 确定四层架构：存储层 → 索引层 → 工具层 → 推理层
   - 推理层采用三框架并行实现策略（Claude Agent SDK / Pydantic AI / LangGraph）

2. **数据模型设计**
   - `PageDocument`: 页面存储模型，支持一页多表
   - `ContentBlock`: 内容块模型（文本/表格/标题/列表）
   - `TableMeta`: 表格元数据，支持跨页标记
   - `Annotation`: 注释模型（注1、方案A 等）

3. **MCP 工具定义**
   - `get_toc`: 获取规程目录树
   - `smart_search`: 混合检索（关键词+语义）
   - `read_page_range`: 读取连续页面（自动跨页拼接）

4. **技术选型**
   - 文档解析：Docling（支持 PDF/DOCX，保留 provenance）
   - 关键词索引：SQLite FTS5
   - 语义索引：LanceDB
   - MCP Server：FastMCP + SSE 传输

### 设计决策记录

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 存储单位 | 页面级 | 保持物理结构，便于引用定位 |
| 存储格式 | JSON + Markdown | JSON 无损结构，Markdown 供 LLM 阅读 |
| 推理框架 | 三框架并行 | Claude SDK 最优体验 + Pydantic AI/LangGraph 企业灵活性 |
| 输入格式 | 仅 DOCX/PDF | 用户保证输入格式，无需转换 |

### 生成文件
- `docs/main/DESIGN_DOCUMENT.md` - 完整设计方案
- `README.md` - 英文版项目说明
- `README_CN.md` - 中文版项目说明
- `CLAUDE.md` - 项目开发指南（Claude Code 配置）

### 待确认事项
- [ ] 需要真实安规文档验证 Docling 解析效果
- [ ] 确认注释格式（注1 vs 注① vs (注一)）
- [ ] 确认是否需要处理图片/公式
