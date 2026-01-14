# RegReader 系统设计与实现文档

> 更新日期: 2026-01-02
> 版本: 0.1.0
> 分支: dev

## 1. 项目概述

### 1.1 项目定位

RegReader 是一个电力系统安全规程智能检索 Agent 系统，采用 **Page-Based Agentic Search** 架构。与传统 RAG 系统不同，RegReader 将文档按页面存储，通过 MCP 协议提供工具接口，让 LLM 动态"翻阅"页面进行多跳检索。

### 1.2 核心设计理念

| 设计原则 | 说明 |
|---------|------|
| **按页存储** | 文档按页存储，保留原始结构，非任意分块 |
| **动态翻阅** | LLM 通过多次工具调用逐步深入，非一次向量匹配 |
| **三框架并行** | Claude Agent SDK / Pydantic AI / LangGraph 三种实现 |
| **MCP 协议** | 所有 Agent 通过 MCP 协议访问数据，不直接操作 PageStore |

### 1.3 技术栈概览

```
┌──────────────────────────────────────────────────────────────┐
│                        CLI Layer (Typer)                      │
├──────────────────────────────────────────────────────────────┤
│                       Agent Layer                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐          │
│  │ Claude Agent │ │ Pydantic AI  │ │  LangGraph   │          │
│  │     SDK      │ │    Agent     │ │    Agent     │          │
│  └──────────────┘ └──────────────┘ └──────────────┘          │
├──────────────────────────────────────────────────────────────┤
│                    MCP Server (FastMCP)                       │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  get_toc | smart_search | read_page_range | ...         │ │
│  └─────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────┤
│                      Index Layer                              │
│  ┌───────────────────────┐ ┌───────────────────────┐         │
│  │    Keyword Index      │ │    Vector Index       │         │
│  │  FTS5/Tantivy/Whoosh  │ │  LanceDB/Qdrant       │         │
│  └───────────────────────┘ └───────────────────────┘         │
│                    ↓ HybridSearch (RRF) ↓                     │
├──────────────────────────────────────────────────────────────┤
│                     Storage Layer                             │
│  ┌───────────────────────┐ ┌───────────────────────┐         │
│  │     PageStore         │ │   DocumentStructure   │         │
│  │  (JSON per page)      │ │   (Chapter Tree)      │         │
│  └───────────────────────┘ └───────────────────────┘         │
├──────────────────────────────────────────────────────────────┤
│                     Parser Layer                              │
│  ┌───────────────────────────────────────────────────────┐   │
│  │              Docling (OCR + Table Structure)           │   │
│  └───────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. 数据模型设计

### 2.1 核心模型层级

```
PageDocument (页面文档 - 核心存储单位)
├── reg_id: str                    # 规程标识
├── page_num: int                  # 页码
├── active_chapters: list[str]     # 本页活跃章节
├── content_blocks: list[ContentBlock]  # 内容块列表
├── content_markdown: str          # 完整页面 Markdown
├── continues_from_prev: bool      # 是否承接上页
├── continues_to_next: bool        # 是否延续下页
└── annotations: list[Annotation]  # 页脚注释

ContentBlock (内容块)
├── block_id: str                  # 唯一标识
├── block_type: BlockType          # text/table/heading/list/section_content
├── content_markdown: str          # Markdown 内容
├── chapter_path: list[str]        # 所属章节路径
└── table_meta: TableMeta | None   # 表格元数据

TableMeta (表格元数据)
├── table_id: str                  # 表格唯一标识
├── caption: str                   # 表格标题
├── is_truncated: bool             # 是否跨页截断
├── cells: list[TableCell]         # 单元格数据
├── master_table_id: str | None    # 跨页表格主ID
└── segment_index: int             # 段落索引
```

### 2.2 章节结构模型

```python
DocumentStructure (全局章节树)
├── reg_id: str
├── all_nodes: dict[str, ChapterNode]  # 所有章节节点映射
├── root_node_ids: list[str]           # 顶级节点ID列表
└── methods:
    ├── get_chapter_path(node_id) -> list[str]
    ├── get_node_by_section_number(section_num) -> ChapterNode
    ├── get_chapter_tree() -> TocTree
    └── iter_all_nodes() -> Iterator[ChapterNode]

ChapterNode (章节节点)
├── node_id: str                   # 节点唯一标识
├── section_number: str            # 编号 (如 "2.1.4")
├── title: str                     # 标题
├── level: int                     # 层级深度
├── page_num: int                  # 起始页码
├── parent_id: str | None          # 父节点ID
├── children_ids: list[str]        # 子节点ID列表
└── content_block_ids: list[str]   # 关联内容块ID
```

### 2.3 检索模型

```python
SearchResult (搜索结果)
├── reg_id: str
├── page_num: int
├── chapter_path: list[str]
├── snippet: str
├── score: float
└── block_id: str | None

TocTree (目录树)
├── reg_id: str
└── items: list[TocItem]

TocItem (目录项)
├── section_number: str
├── title: str
├── level: int
├── page_range: tuple[int, int]
└── children: list[TocItem]
```

---

## 3. 存储层实现

### 3.1 PageStore

**文件**: `src/regreader/storage/page_store.py`

**存储结构**:
```
data/storage/
├── pages/
│   ├── {reg_id}/
│   │   ├── page_001.json
│   │   ├── page_002.json
│   │   └── ...
│   └── ...
├── structures/
│   └── {reg_id}_structure.json
├── tables/
│   └── {reg_id}_tables.json
└── index/
    ├── fts5.db
    └── lancedb/
```

**核心方法**:
```python
class PageStore:
    def save_page(self, page: PageDocument) -> None
    def load_page(self, reg_id: str, page_num: int) -> PageDocument
    def load_page_range(self, reg_id: str, start: int, end: int) -> list[PageDocument]
    def save_structure(self, structure: DocumentStructure) -> None
    def load_structure(self, reg_id: str) -> DocumentStructure
    def save_table_registry(self, registry: TableRegistry) -> None
    def load_table_registry(self, reg_id: str) -> TableRegistry
    def list_regulations(self) -> list[str]
    def delete_regulation(self, reg_id: str) -> None
    def get_page_count(self, reg_id: str) -> int
```

### 3.2 表格注册表

**TableRegistry** 提供 O(1) 表格查找能力:

```python
class TableRegistry:
    tables: dict[str, TableMeta]           # table_id -> TableMeta
    segment_to_table: dict[str, str]       # segment_id -> master_table_id
    page_to_tables: dict[int, list[str]]   # page_num -> list[table_id]

    def get_table(self, table_id: str) -> TableMeta
    def get_tables_on_page(self, page_num: int) -> list[TableMeta]
    def get_full_table(self, table_id: str) -> TableMeta  # 合并跨页表格
```

---

## 4. 索引层实现

### 4.1 抽象接口

**文件**: `src/regreader/index/base.py`

```python
class BaseKeywordIndex(ABC):
    @abstractmethod
    def index_page(self, page: PageDocument, doc_structure: DocumentStructure | None = None) -> None

    @abstractmethod
    def search(
        self,
        query: str,
        reg_id: str | None = None,
        chapter_scope: str | None = None,
        limit: int = 10,
        block_types: list[str] | None = None,
        section_number: str | None = None,
    ) -> list[SearchResult]

    @abstractmethod
    def delete_regulation(self, reg_id: str) -> None

class BaseVectorIndex(ABC):
    # 相同接口，额外提供 embedding_dimension 属性
    @property
    @abstractmethod
    def embedding_dimension(self) -> int
```

### 4.2 关键词索引实现

#### FTS5Index (默认)

**文件**: `src/regreader/index/keyword/fts5.py`

```python
class FTS5Index(BaseKeywordIndex):
    """SQLite FTS5 全文搜索索引"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        # 创建 FTS5 虚拟表
        CREATE VIRTUAL TABLE IF NOT EXISTS content_fts USING fts5(
            reg_id,
            page_num,
            block_id,
            block_type,
            chapter_path,
            section_number,
            content,
            tokenize='porter unicode61'
        )
```

#### TantivyIndex (可选)

**文件**: `src/regreader/index/keyword/tantivy.py`

- 使用 Rust Tantivy 引擎
- 高性能，支持复杂查询语法
- 需要: `pip install regreader[tantivy]`

#### WhooshIndex (可选)

**文件**: `src/regreader/index/keyword/whoosh.py`

- 纯 Python 实现
- 支持中文分词 (jieba)
- 需要: `pip install regreader[whoosh]`

### 4.3 向量索引实现

#### LanceDBIndex (默认)

**文件**: `src/regreader/index/vector/lancedb.py`

```python
class LanceDBIndex(BaseVectorIndex):
    """LanceDB 向量索引"""

    def __init__(self, db_path: Path, embedding: BaseEmbedding):
        self.db = lancedb.connect(db_path)
        self.embedding = embedding

    def index_page(self, page: PageDocument, ...):
        # 为每个内容块生成向量
        for block in page.content_blocks:
            vector = self.embedding.embed_query(block.content_markdown)
            # 存储到 LanceDB
```

#### QdrantIndex (可选)

**文件**: `src/regreader/index/vector/qdrant.py`

- 支持本地磁盘或远程服务器模式
- 需要: `pip install regreader[qdrant]`

### 4.4 混合检索

**文件**: `src/regreader/index/hybrid_search.py`

```python
class HybridSearch:
    """RRF 混合检索器"""

    def __init__(
        self,
        keyword_index: BaseKeywordIndex,
        vector_index: BaseVectorIndex,
        keyword_weight: float = 0.4,
        vector_weight: float = 0.6,
    ):
        self.keyword_index = keyword_index
        self.vector_index = vector_index
        self.keyword_weight = keyword_weight
        self.vector_weight = vector_weight

    def search(self, query: str, ...) -> list[SearchResult]:
        # 1. 关键词检索
        keyword_results = self.keyword_index.search(query, ...)

        # 2. 向量检索
        vector_results = self.vector_index.search(query, ...)

        # 3. RRF 合并
        return self._merge_results(keyword_results, vector_results)

    def _merge_results(self, kw_results, vec_results) -> list[SearchResult]:
        """Reciprocal Rank Fusion"""
        k = 60  # RRF 常数
        scores = {}

        for rank, result in enumerate(kw_results):
            key = (result.reg_id, result.page_num, result.block_id)
            scores[key] = scores.get(key, 0) + self.keyword_weight / (k + rank + 1)

        for rank, result in enumerate(vec_results):
            key = (result.reg_id, result.page_num, result.block_id)
            scores[key] = scores.get(key, 0) + self.vector_weight / (k + rank + 1)

        # 按分数排序返回
        ...
```

---

## 5. Embedding 层实现

### 5.1 抽象接口

**文件**: `src/regreader/embedding/base.py`

```python
class BaseEmbedding(ABC):
    @property
    @abstractmethod
    def dimension(self) -> int:
        """向量维度"""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """单文本嵌入"""

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量文本嵌入"""
```

### 5.2 实现

#### SentenceTransformerEmbedding (默认)

**文件**: `src/regreader/embedding/sentence_transformer.py`

```python
class SentenceTransformerEmbedding(BaseEmbedding):
    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        self.model = SentenceTransformer(model_name)

    @property
    def dimension(self) -> int:
        return self.model.get_sentence_embedding_dimension()

    def embed_query(self, text: str) -> list[float]:
        return self.model.encode(text, normalize_embeddings=True).tolist()
```

#### FlagEmbedding (可选)

**文件**: `src/regreader/embedding/flag.py`

- 使用 FlagEmbedding 库
- 需要: `pip install regreader[flag]`

---

## 6. MCP 工具层实现

### 6.1 工具分类体系

| 阶段 | 工具名称 | 功能说明 |
|------|---------|---------|
| Phase 0 | `get_toc` | 获取规程目录树 |
| Phase 0 | `smart_search` | 混合检索 (关键词 + 语义) |
| Phase 0 | `read_page_range` | 读取连续页面内容 |
| Phase 1 | `lookup_annotation` | 查找注释内容 |
| Phase 1 | `search_tables` | 表格搜索 |
| Phase 1 | `resolve_reference` | 解析交叉引用 |
| Phase 2 | `search_annotations` | 搜索所有注释 |
| Phase 2 | `get_table_by_id` | 按ID获取完整表格 |
| Phase 2 | `get_block_with_context` | 读取内容块及上下文 |
| Phase 3 | `find_similar_content` | 语义相似内容查找 |
| Phase 3 | `compare_sections` | 章节对比分析 |
| Nav | `get_tool_guide` | 工具使用指南 |
| Nav | `get_chapter_structure` | 完整章节结构 |
| Nav | `read_chapter_content` | 读取指定章节内容 |

### 6.2 核心工具实现

**文件**: `src/regreader/mcp/tools.py`

```python
class RegReaderTools:
    def __init__(self):
        self.page_store = PageStore()
        self.hybrid_search = HybridSearch(...)

    def get_toc(self, reg_id: str) -> dict:
        """获取规程目录树"""
        structure = self.page_store.load_structure(reg_id)
        return structure.get_chapter_tree().model_dump()

    def smart_search(
        self,
        query: str,
        reg_id: str,
        chapter_scope: str | None = None,
        limit: int = 10,
        block_types: list[str] | None = None,
        section_number: str | None = None,
    ) -> list[dict]:
        """混合检索"""
        results = self.hybrid_search.search(
            query=query,
            reg_id=reg_id,
            chapter_scope=chapter_scope,
            limit=limit,
            block_types=block_types,
            section_number=section_number,
        )
        return [r.model_dump() for r in results]

    def read_page_range(
        self,
        reg_id: str,
        start_page: int,
        end_page: int,
    ) -> dict:
        """读取连续页面"""
        if end_page - start_page > 10:
            raise InvalidPageRangeError("单次最多读取 10 页")

        pages = self.page_store.load_page_range(reg_id, start_page, end_page)
        return {
            "pages": [p.model_dump() for p in pages],
            "total_pages": len(pages),
        }

    def lookup_annotation(
        self,
        reg_id: str,
        annotation_id: str,
        page_hint: int | None = None,
    ) -> dict:
        """查找注释内容"""
        # 支持变体匹配: 注1, 注①, 注一
        normalized_id = self._normalize_annotation_id(annotation_id)

        if page_hint:
            # 优先在提示页查找
            page = self.page_store.load_page(reg_id, page_hint)
            for ann in page.annotations:
                if self._match_annotation(ann, normalized_id):
                    return ann.model_dump()

        # 全局搜索
        ...

    def resolve_reference(
        self,
        reg_id: str,
        reference_text: str,
    ) -> dict:
        """解析交叉引用"""
        # 支持多种引用格式:
        # - "见第六章" -> 章节引用
        # - "见表 2-1" -> 表格引用
        # - "见 2.1.4 条" -> 条款引用
        # - "见注 1" -> 注释引用
        # - "见附录 A" -> 附录引用

        patterns = [
            (r"见第(\S+)章", "chapter"),
            (r"见表\s*(\S+)", "table"),
            (r"见\s*([\d.]+)\s*条?", "section"),
            (r"见注\s*(\d+)", "annotation"),
            (r"见附录\s*([A-Z])", "appendix"),
        ]

        for pattern, ref_type in patterns:
            match = re.search(pattern, reference_text)
            if match:
                return self._resolve_by_type(reg_id, ref_type, match.group(1))

        raise ReferenceResolutionError(f"无法解析引用: {reference_text}")
```

### 6.3 MCP Server 实现

**文件**: `src/regreader/mcp/server.py`

```python
from mcp.server.fastmcp import FastMCP

def create_mcp_server(
    host: str = "127.0.0.1",
    port: int = 8080,
) -> FastMCP:
    mcp = FastMCP(
        name="regreader",
        host=host,
        port=port,
    )

    tools = RegReaderTools()

    @mcp.tool(meta=TOOL_METADATA["get_toc"].to_dict())
    def get_toc(reg_id: str) -> dict:
        return tools.get_toc(reg_id)

    @mcp.tool(meta=TOOL_METADATA["smart_search"].to_dict())
    def smart_search(
        query: str,
        reg_id: str,
        chapter_scope: str | None = None,
        limit: int = 10,
        block_types: list[str] | None = None,
        section_number: str | None = None,
    ) -> list[dict]:
        return tools.smart_search(
            query, reg_id, chapter_scope, limit, block_types, section_number
        )

    # ... 其他工具注册

    return mcp
```

---

## 7. Agent 层实现

### 7.1 抽象基类

**文件**: `src/regreader/agents/base.py`

```python
class AgentResponse(BaseModel):
    """Agent 响应"""
    content: str
    sources: list[str]
    tool_calls: list[dict]
    thinking: str | None = None

class BaseRegReaderAgent(ABC):
    """RegReader Agent 抽象基类"""

    @abstractmethod
    async def chat(self, message: str) -> AgentResponse:
        """发送消息并获取响应"""

    @abstractmethod
    async def reset(self) -> None:
        """重置对话历史"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent 名称"""

    @property
    @abstractmethod
    def model(self) -> str:
        """使用的模型"""
```

### 7.2 Claude Agent SDK 实现

**文件**: `src/regreader/agents/claude_agent.py`

```python
class ClaudeAgent(BaseRegReaderAgent):
    """Claude Agent SDK 实现"""

    def __init__(
        self,
        reg_id: str,
        model: str = "claude-sonnet-4-20250514",
        mcp_config: MCPConnectionConfig | None = None,
    ):
        self.reg_id = reg_id
        self._model = model
        self.mcp_config = mcp_config or MCPConnectionConfig.stdio()
        self.memory = AgentMemory()
        self._agent = None

    async def _init_agent(self):
        from claude_agent_sdk import Agent, MCPServerStdio

        self._agent = Agent(
            model=self._model,
            mcp_servers=[
                MCPServerStdio(
                    command="regreader",
                    args=["serve", "--transport", "stdio"],
                )
            ],
            system_prompt=self._get_system_prompt(),
        )

    async def chat(self, message: str) -> AgentResponse:
        if not self._agent:
            await self._init_agent()

        self.memory.add_user_message(message)

        response = await self._agent.chat(
            message,
            history=self.memory.get_history(),
        )

        self.memory.add_assistant_message(response.content)

        return AgentResponse(
            content=response.content,
            sources=response.sources,
            tool_calls=response.tool_calls,
            thinking=response.thinking,
        )

    @property
    def name(self) -> str:
        return "claude"

    @property
    def model(self) -> str:
        return self._model
```

### 7.3 Pydantic AI 实现

**文件**: `src/regreader/agents/pydantic_agent.py`

```python
class PydanticAIAgent(BaseRegReaderAgent):
    """Pydantic AI 实现"""

    def __init__(
        self,
        reg_id: str,
        model: str = "claude-sonnet-4-20250514",
        mcp_config: MCPConnectionConfig | None = None,
    ):
        self.reg_id = reg_id
        self._model = model
        self.mcp_config = mcp_config or MCPConnectionConfig.stdio()
        self.memory = AgentMemory()
        self._agent = None

    async def _init_agent(self):
        from pydantic_ai import Agent
        from pydantic_ai.mcp import MCPServerStdio

        self._agent = Agent(
            self._model,
            mcp_servers=[
                MCPServerStdio(
                    command="regreader",
                    args=["serve", "--transport", "stdio"],
                )
            ],
            system_prompt=self._get_system_prompt(),
        )

    async def chat(self, message: str) -> AgentResponse:
        if not self._agent:
            await self._init_agent()

        self.memory.add_user_message(message)

        async with self._agent.run_stream(
            message,
            message_history=self.memory.get_pydantic_history(),
        ) as stream:
            content = ""
            async for chunk in stream.stream_text():
                content += chunk

        result = stream.result
        self.memory.add_assistant_message(content)

        return AgentResponse(
            content=content,
            sources=self._extract_sources(result),
            tool_calls=self._extract_tool_calls(result),
        )

    @property
    def name(self) -> str:
        return "pydantic"

    @property
    def model(self) -> str:
        return self._model
```

### 7.4 LangGraph 实现

**文件**: `src/regreader/agents/langgraph_agent.py`

```python
class LangGraphAgent(BaseRegReaderAgent):
    """LangGraph 实现"""

    def __init__(
        self,
        reg_id: str,
        model: str = "claude-sonnet-4-20250514",
        mcp_config: MCPConnectionConfig | None = None,
    ):
        self.reg_id = reg_id
        self._model = model
        self.mcp_config = mcp_config or MCPConnectionConfig.stdio()
        self.memory = AgentMemory()
        self._graph = None

    async def _init_graph(self):
        from langgraph.graph import StateGraph, START, END
        from langchain_anthropic import ChatAnthropic

        # 创建 LLM
        llm = ChatAnthropic(model=self._model)

        # 绑定 MCP 工具
        tools = await self._load_mcp_tools()
        llm_with_tools = llm.bind_tools(tools)

        # 定义状态图
        builder = StateGraph(AgentState)
        builder.add_node("agent", self._agent_node)
        builder.add_node("tools", self._tool_node)

        builder.add_edge(START, "agent")
        builder.add_conditional_edges(
            "agent",
            self._should_call_tools,
            {"tools": "tools", "end": END},
        )
        builder.add_edge("tools", "agent")

        self._graph = builder.compile()

    async def chat(self, message: str) -> AgentResponse:
        if not self._graph:
            await self._init_graph()

        self.memory.add_user_message(message)

        state = AgentState(
            messages=self.memory.get_langchain_history() + [
                HumanMessage(content=message)
            ]
        )

        result = await self._graph.ainvoke(state)

        content = result["messages"][-1].content
        self.memory.add_assistant_message(content)

        return AgentResponse(
            content=content,
            sources=self._extract_sources(result),
            tool_calls=self._extract_tool_calls(result),
        )

    @property
    def name(self) -> str:
        return "langgraph"

    @property
    def model(self) -> str:
        return self._model
```

### 7.5 对话历史管理

**文件**: `src/regreader/agents/memory.py`

```python
class ContentChunk(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    timestamp: datetime

class AgentMemory:
    """多轮对话历史管理"""

    def __init__(self, max_chunks: int = 100):
        self.chunks: list[ContentChunk] = []
        self.max_chunks = max_chunks

    def add_user_message(self, content: str) -> None:
        self.chunks.append(ContentChunk(
            role="user",
            content=content,
            timestamp=datetime.now(),
        ))
        self._trim()

    def add_assistant_message(self, content: str) -> None:
        self.chunks.append(ContentChunk(
            role="assistant",
            content=content,
            timestamp=datetime.now(),
        ))
        self._trim()

    def get_history(self) -> list[dict]:
        return [{"role": c.role, "content": c.content} for c in self.chunks]

    def get_pydantic_history(self) -> list:
        """转换为 Pydantic AI 格式"""
        from pydantic_ai.messages import ModelRequest, ModelResponse
        ...

    def get_langchain_history(self) -> list:
        """转换为 LangChain 格式"""
        from langchain_core.messages import HumanMessage, AIMessage
        ...

    def clear(self) -> None:
        self.chunks.clear()

    def _trim(self) -> None:
        if len(self.chunks) > self.max_chunks:
            self.chunks = self.chunks[-self.max_chunks:]
```

---

## 8. CLI 实现

### 8.1 命令结构

**文件**: `src/regreader/cli.py`

```python
import typer
from rich.console import Console

app = typer.Typer(name="regreader", help="RegReader CLI")
console = Console()

# 文档管理命令
@app.command()
def ingest(
    file: Path = typer.Option(None, "--file", "-f"),
    directory: Path = typer.Option(None, "--dir", "-d"),
    reg_id: str = typer.Option(..., "--reg-id", "-r"),
    format: str = typer.Option("pdf", "--format"),
):
    """导入文档到系统"""
    ...

@app.command()
def list():
    """列出所有规程"""
    ...

@app.command()
def delete(reg_id: str):
    """删除规程"""
    ...

# MCP Server 命令
@app.command()
def serve(
    transport: str = typer.Option("stdio", "--transport", "-t"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8080, "--port", "-p"),
):
    """启动 MCP Server"""
    ...

# 检索命令
@app.command()
def search(
    query: str,
    reg_id: str = typer.Option(None, "--reg-id", "-r"),
    chapter: str = typer.Option(None, "--chapter"),
    limit: int = typer.Option(10, "--limit", "-l"),
    types: str = typer.Option(None, "--types"),
):
    """执行搜索"""
    ...

# Agent 命令
@app.command()
def chat(
    reg_id: str = typer.Option(..., "--reg-id", "-r"),
    agent: str = typer.Option("pydantic", "--agent", "-a"),
    model: str = typer.Option(None, "--model", "-m"),
):
    """启动交互式对话"""
    ...

@app.command()
def ask(
    question: str,
    reg_id: str = typer.Option(..., "--reg-id", "-r"),
    agent: str = typer.Option("pydantic", "--agent", "-a"),
    json_output: bool = typer.Option(False, "--json"),
):
    """单次查询"""
    ...

# MCP 工具命令 (CLI 接口)
@app.command()
def toc(
    reg_id: str,
    level: int = typer.Option(None, "--level", "-l"),
    expand: bool = typer.Option(False, "--expand"),
):
    """获取目录"""
    ...

@app.command("read-pages")
def read_pages(
    reg_id: str = typer.Option(..., "--reg-id", "-r"),
    start: int = typer.Option(..., "--start", "-s"),
    end: int = typer.Option(..., "--end", "-e"),
):
    """读取页面范围"""
    ...

# ... 更多命令
```

---

## 9. 配置系统

### 9.1 配置类

**文件**: `src/regreader/config.py`

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class RegReaderSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="REGREADER_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # 存储路径
    data_dir: Path = Path("./data/storage")
    pages_dir: Path = Path("./data/storage/pages")
    index_dir: Path = Path("./data/storage/index")

    # 嵌入模型
    embedding_backend: str = "sentence_transformer"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dimension: int = 512

    # MCP
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8080
    mcp_transport: str = "stdio"

    # LLM
    llm_model_name: str = "claude-sonnet-4-20250514"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.anthropic.com"

    # 索引后端
    keyword_index_backend: str = "fts5"
    vector_index_backend: str = "lancedb"

    # 检索权重
    fts_weight: float = 0.4
    vector_weight: float = 0.6
    search_top_k: int = 10

    # 计算属性
    @property
    def fts_db_path(self) -> Path:
        return self.index_dir / "fts5.db"

    @property
    def lancedb_path(self) -> Path:
        return self.index_dir / "lancedb"

    def get_llm_provider(self) -> str:
        """推断 LLM 提供商"""
        if "anthropic" in self.llm_base_url:
            return "anthropic"
        elif "openai" in self.llm_base_url:
            return "openai"
        elif "google" in self.llm_base_url:
            return "google"
        return "unknown"

# 全局单例
settings = RegReaderSettings()
```

---

## 10. 异常体系

**文件**: `src/regreader/exceptions.py`

```python
class RegReaderError(Exception):
    """RegReader 基础异常"""
    pass

class ParserError(RegReaderError):
    """文档解析错误"""
    pass

class StorageError(RegReaderError):
    """存储操作错误"""
    pass

class IndexError(RegReaderError):
    """索引操作错误"""
    pass

class RegulationNotFoundError(RegReaderError):
    """规程不存在"""
    def __init__(self, reg_id: str):
        super().__init__(f"规程不存在: {reg_id}")
        self.reg_id = reg_id

class PageNotFoundError(RegReaderError):
    """页面不存在"""
    def __init__(self, reg_id: str, page_num: int):
        super().__init__(f"页面不存在: {reg_id} 第 {page_num} 页")
        self.reg_id = reg_id
        self.page_num = page_num

class InvalidPageRangeError(RegReaderError):
    """无效页码范围"""
    pass

class ChapterNotFoundError(RegReaderError):
    """章节不存在"""
    def __init__(self, reg_id: str, section_number: str):
        super().__init__(f"章节不存在: {reg_id} {section_number}")
        self.reg_id = reg_id
        self.section_number = section_number

class AnnotationNotFoundError(RegReaderError):
    """注释不存在"""
    def __init__(self, reg_id: str, annotation_id: str):
        super().__init__(f"注释不存在: {reg_id} {annotation_id}")
        self.reg_id = reg_id
        self.annotation_id = annotation_id

class TableNotFoundError(RegReaderError):
    """表格不存在"""
    def __init__(self, reg_id: str, table_id: str):
        super().__init__(f"表格不存在: {reg_id} {table_id}")
        self.reg_id = reg_id
        self.table_id = table_id

class ReferenceResolutionError(RegReaderError):
    """交叉引用解析错误"""
    def __init__(self, reference_text: str):
        super().__init__(f"无法解析引用: {reference_text}")
        self.reference_text = reference_text
```

---

## 11. 实现状态汇总

### 11.1 已完成模块

| 模块 | 状态 | 说明 |
|------|------|------|
| storage/models.py | ✅ 完成 | 核心数据模型 |
| storage/page_store.py | ✅ 完成 | 页面持久化存储 |
| index/base.py | ✅ 完成 | 索引抽象基类 |
| index/keyword/fts5.py | ✅ 完成 | FTS5 关键词索引 |
| index/vector/lancedb.py | ✅ 完成 | LanceDB 向量索引 |
| index/hybrid_search.py | ✅ 完成 | RRF 混合检索 |
| index/table_search.py | ✅ 完成 | 表格混合检索 |
| embedding/base.py | ✅ 完成 | 嵌入抽象基类 |
| embedding/sentence_transformer.py | ✅ 完成 | ST 嵌入实现 |
| mcp/tools.py | ✅ 完成 | MCP 工具实现 |
| mcp/server.py | ✅ 完成 | MCP Server |
| mcp/tool_metadata.py | ✅ 完成 | 工具元数据 |
| agents/base.py | ✅ 完成 | Agent 抽象基类 |
| agents/claude_agent.py | ✅ 完成 | Claude Agent |
| agents/pydantic_agent.py | ✅ 完成 | Pydantic AI Agent |
| agents/langgraph_agent.py | ✅ 完成 | LangGraph Agent |
| agents/memory.py | ✅ 完成 | 对话历史管理 |
| agents/display.py | ✅ 完成 | 状态显示 |
| parser/docling_parser.py | ✅ 完成 | 文档解析 |
| parser/page_extractor.py | ✅ 完成 | 页面提取 |
| config.py | ✅ 完成 | 配置系统 |
| exceptions.py | ✅ 完成 | 异常体系 |
| cli.py | ✅ 完成 | CLI 命令 |

### 11.2 可选模块

| 模块 | 状态 | 依赖 |
|------|------|------|
| index/keyword/tantivy.py | ✅ 可用 | `regreader[tantivy]` |
| index/keyword/whoosh.py | ✅ 可用 | `regreader[whoosh]` |
| index/vector/qdrant.py | ✅ 可用 | `regreader[qdrant]` |
| embedding/flag.py | ✅ 可用 | `regreader[flag]` |

---

## 12. 技术亮点

### 12.1 架构设计

1. **Page-Based 存储**: 保留文档原始结构，支持跨页内容处理
2. **可插拔索引**: 支持多种关键词和向量索引后端，易于扩展
3. **MCP 协议标准化**: 工具接口统一，多 Agent 框架复用
4. **三框架并行**: 同时支持 Claude SDK、Pydantic AI、LangGraph

### 12.2 数据处理

1. **跨页表格自动合并**: 识别并拼接跨页表格
2. **章节结构树**: 完整的层级关系和内容块关联
3. **O(1) 表格查找**: 通过注册表快速定位

### 12.3 检索优化

1. **RRF 混合检索**: 结合关键词和语义检索优势
2. **章节范围限定**: 精确控制检索范围
3. **块类型过滤**: 支持 text/table/heading 等类型过滤

### 12.4 工具设计

1. **分阶段工具体系**: 基础 → 多跳 → 上下文 → 发现
2. **交叉引用智能解析**: 正则 + 匹配多种引用格式
3. **注释变体匹配**: 支持 注1/注①/注一 等变体

---

## 附录 A: 依赖清单

```toml
[project.dependencies]
# 核心依赖
docling>=2.22.0
pydantic>=2.10.0
pydantic-settings>=2.7.0
lancedb>=0.20.0
mcp>=1.6.0
typer>=0.15.0
rich>=13.9.0
loguru>=0.7.0

# Agent 框架
anthropic>=0.52.0
claude-agent-sdk>=0.1.0
pydantic-ai>=1.0.0
langgraph>=0.2.0
langchain-anthropic>=0.3.0
langchain-openai>=0.2.0

# 向量嵌入
sentence-transformers>=3.3.0
```

## 附录 B: 环境变量参考

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| REGREADER_DATA_DIR | ./data/storage | 数据目录 |
| REGREADER_EMBEDDING_BACKEND | sentence_transformer | 嵌入后端 |
| REGREADER_EMBEDDING_MODEL | BAAI/bge-small-zh-v1.5 | 嵌入模型 |
| REGREADER_MCP_HOST | 127.0.0.1 | MCP 主机 |
| REGREADER_MCP_PORT | 8080 | MCP 端口 |
| REGREADER_MCP_TRANSPORT | stdio | MCP 传输方式 |
| REGREADER_LLM_MODEL_NAME | claude-sonnet-4-20250514 | LLM 模型 |
| REGREADER_LLM_API_KEY | - | LLM API Key |
| REGREADER_KEYWORD_INDEX_BACKEND | fts5 | 关键词索引后端 |
| REGREADER_VECTOR_INDEX_BACKEND | lancedb | 向量索引后端 |
| REGREADER_FTS_WEIGHT | 0.4 | FTS 权重 |
| REGREADER_VECTOR_WEIGHT | 0.6 | 向量权重 |
