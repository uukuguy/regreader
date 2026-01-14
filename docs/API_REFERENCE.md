# RegReader API 参考文档

本文档提供 RegReader 核心模块的 API 参考。

## 目录

- [存储层 (Storage Layer)](#存储层-storage-layer)
  - [PageStore](#pagestore)
  - [数据模型](#数据模型)
- [索引层 (Index Layer)](#索引层-index-layer)
  - [HybridSearch](#hybridsearch)
  - [TableHybridSearch](#tablehybridsearch)
- [MCP工具层 (MCP Tools Layer)](#mcp工具层-mcp-tools-layer)
  - [RegReaderTools](#regreadertools)
- [编排层 (Orchestrator Layer)](#编排层-orchestrator-layer)
  - [Coordinator](#coordinator)
  - [QueryAnalyzer](#queryanalyzer)
- [基础设施层 (Infrastructure Layer)](#基础设施层-infrastructure-layer)
  - [FileContext](#filecontext)
  - [EventBus](#eventbus)
  - [SkillLoader](#skillloader)
  - [SecurityGuard](#securityguard)
- [子代理层 (Subagents Layer)](#子代理层-subagents-layer)
  - [BaseSubagent](#basesubagent)
  - [RegSearchSubagent](#regsearchsubagent)

---

## 存储层 (Storage Layer)

### PageStore

**位置**: `src/regreader/storage/page_store.py`

页面存储管理器，负责页面级别的文档存储和检索。

#### 初始化

```python
from regreader.storage import PageStore

store = PageStore(
    base_dir: Path | None = None  # 存储根目录，默认 data/storage/pages
)
```

#### 主要方法

##### `save_page(page: PageDocument) -> None`

保存单个页面文档。

**参数**:
- `page` (PageDocument): 页面文档对象

**示例**:
```python
from regreader.storage.models import PageDocument, ContentBlock

page = PageDocument(
    reg_id="angui_2024",
    page_num=85,
    chapter_path=["第六章", "故障处理", "母线故障"],
    content_blocks=[
        ContentBlock(type="text", content="母线失压处理方法...")
    ]
)
store.save_page(page)
```

##### `load_page(reg_id: str, page_num: int) -> PageDocument`

加载指定页面。

**参数**:
- `reg_id` (str): 规程标识
- `page_num` (int): 页码

**返回**: PageDocument

**异常**:
- `PageNotFoundError`: 页面不存在

##### `load_page_range(reg_id: str, start: int, end: int) -> list[PageDocument]`

加载页面范围。

**参数**:
- `reg_id` (str): 规程标识
- `start` (int): 起始页码
- `end` (int): 结束页码（包含）

**返回**: 页面列表

**异常**:
- `InvalidPageRangeError`: 页码范围无效

##### `load_toc(reg_id: str) -> TocTree`

加载规程目录树。

**参数**:
- `reg_id` (str): 规程标识

**返回**: TocTree 对象

**异常**:
- `RegulationNotFoundError`: 规程不存在

##### `save_toc(reg_id: str, toc: TocTree) -> None`

保存规程目录树。

**参数**:
- `reg_id` (str): 规程标识
- `toc` (TocTree): 目录树对象

---

### 数据模型

**位置**: `src/regreader/storage/models.py`

#### PageDocument

页面文档模型。

```python
from regreader.storage.models import PageDocument

class PageDocument(BaseModel):
    reg_id: str                        # 规程标识
    page_num: int                      # 页码
    chapter_path: list[str]            # 章节路径
    content_blocks: list[ContentBlock] # 内容块列表
    continues_to_next: bool = False    # 是否跨页续表
    annotations: list[Annotation] = [] # 注释列表
    metadata: dict[str, Any] = {}      # 元数据
```

#### ContentBlock

内容块模型，支持文本、表格、标题等类型。

```python
class ContentBlock(BaseModel):
    type: Literal["text", "table", "heading", "list", "section_content"]
    content: str | None = None         # 文本内容（Markdown）
    table_meta: TableMeta | None = None # 表格元数据
    level: int | None = None           # 标题级别
```

#### TableMeta

表格元数据模型。

```python
class TableMeta(BaseModel):
    table_id: str                      # 表格唯一标识
    caption: str | None                # 表格标题
    markdown: str                      # Markdown格式表格
    cells: list[list[str]]             # 单元格内容
    continues_to_next: bool = False    # 跨页标记
```

#### TocTree

目录树模型。

```python
class TocTree(BaseModel):
    title: str                         # 规程标题
    items: list[TocItem]               # 顶层目录项
    total_pages: int | None = None     # 总页数
```

#### SearchResult

搜索结果模型。

```python
class SearchResult(BaseModel):
    reg_id: str                        # 规程标识
    page_num: int                      # 页码
    snippet: str                       # 摘要
    score: float                       # 相关度分数
    block_id: str | None = None        # 内容块标识
```

---

## 索引层 (Index Layer)

### HybridSearch

**位置**: `src/regreader/index/hybrid_search.py`

混合检索引擎，融合关键词和向量检索。

#### 初始化

```python
from regreader.index import HybridSearch

search = HybridSearch(
    keyword_backend: str = "fts5",     # 关键词索引: fts5/tantivy/whoosh
    vector_backend: str = "lancedb",   # 向量索引: lancedb/qdrant
    fts_weight: float = 0.4,           # 关键词权重
    vector_weight: float = 0.6         # 向量权重
)
```

#### 主要方法

##### `index_documents(reg_id: str, pages: list[PageDocument]) -> None`

索引文档页面。

**参数**:
- `reg_id` (str): 规程标识
- `pages` (list[PageDocument]): 页面列表

##### `search(query: str, reg_id: str, limit: int = 10, **kwargs) -> list[SearchResult]`

执行混合检索。

**参数**:
- `query` (str): 查询文本
- `reg_id` (str): 规程标识
- `limit` (int): 返回结果数
- `chapter_scope` (str, optional): 章节范围
- `block_types` (list[str], optional): 内容块类型过滤

**返回**: 搜索结果列表

**示例**:
```python
results = search.search(
    query="母线失压处理",
    reg_id="angui_2024",
    limit=10,
    chapter_scope="第六章",
    block_types=["text", "table"]
)

for result in results:
    print(f"页码: {result.page_num}, 分数: {result.score:.2f}")
    print(f"摘要: {result.snippet}")
```

---

### TableHybridSearch

**位置**: `src/regreader/index/table_search.py`

表格专用混合检索。

#### 主要方法

##### `search_tables(query: str, reg_id: str, mode: str = "hybrid", limit: int = 10) -> list[TableSearchResult]`

搜索表格内容。

**参数**:
- `query` (str): 查询文本
- `reg_id` (str): 规程标识
- `mode` (str): 检索模式 - "keyword"、"vector"、"hybrid"
- `limit` (int): 返回结果数

**返回**: 表格搜索结果列表

---

## MCP工具层 (MCP Tools Layer)

### RegReaderTools

**位置**: `src/regreader/mcp/tools.py`

MCP工具集，提供16+工具供Agent调用。

#### 初始化

```python
from regreader.mcp.tools import RegReaderTools

tools = RegReaderTools(
    page_store: PageStore | None = None,
    hybrid_search: HybridSearch | None = None,
    table_search: TableHybridSearch | None = None
)
```

#### 核心工具

##### `get_toc(reg_id: str, max_depth: int = 3, expand_section: str | None = None) -> dict`

获取规程目录树。

**参数**:
- `reg_id` (str): 规程标识
- `max_depth` (int): 目录深度（1-3）
- `expand_section` (str, optional): 完整展开的章节编号

**返回**: 目录树字典

**示例**:
```python
toc = tools.get_toc(
    reg_id="angui_2024",
    max_depth=3,
    expand_section="2.1.4"
)
```

##### `smart_search(query: str, reg_id: str, chapter_scope: str | None = None, limit: int = 10, block_types: list[str] | None = None, section_number: str | None = None) -> list[dict]`

智能检索。

**参数**:
- `query` (str): 查询文本
- `reg_id` (str): 规程标识
- `chapter_scope` (str, optional): 章节范围（如"第六章"）
- `limit` (int): 结果数量
- `block_types` (list[str], optional): 内容类型过滤
- `section_number` (str, optional): 精确章节编号（如"2.1.4.1.6"）

**返回**: 搜索结果列表

##### `read_page_range(reg_id: str, start_page: int, end_page: int) -> dict`

读取页面范围，自动拼接跨页表格。

**参数**:
- `reg_id` (str): 规程标识
- `start_page` (int): 起始页码
- `end_page` (int): 结束页码

**返回**: 页面内容字典

#### 多跳工具

##### `lookup_annotation(reg_id: str, annotation_id: str, page_hint: int | None = None) -> dict`

查找注释。

**参数**:
- `reg_id` (str): 规程标识
- `annotation_id` (str): 注释标识（如"注1"）
- `page_hint` (int, optional): 页码提示

**返回**: 注释内容

##### `search_tables(query: str, reg_id: str, mode: str = "hybrid", limit: int = 10) -> list[dict]`

搜索表格。

**参数**:
- `query` (str): 查询文本
- `reg_id` (str): 规程标识
- `mode` (str): 检索模式
- `limit` (int): 结果数量

**返回**: 表格搜索结果

##### `resolve_reference(reg_id: str, reference_text: str) -> dict`

解析交叉引用（如"见第六章"）。

**参数**:
- `reg_id` (str): 规程标识
- `reference_text` (str): 引用文本

**返回**: 引用目标内容

---

## 编排层 (Orchestrator Layer)

### Coordinator

**位置**: `src/regreader/orchestrator/coordinator.py`

协调器，负责会话管理和事件记录。

#### 初始化

```python
from regreader.orchestrator.coordinator import Coordinator

coordinator = Coordinator(
    work_dir: Path | None = None,      # 工作目录，默认 coordinator/
    event_bus: EventBus | None = None  # 事件总线
)
```

#### 主要方法

##### `record_query(query: str, hints: dict[str, Any] | None = None) -> None`

记录查询到 plan.md。

**参数**:
- `query` (str): 查询文本
- `hints` (dict, optional): 提取的提示信息

##### `update_session(reg_id: str | None = None, sources: list[str] | None = None) -> None`

更新会话状态。

**参数**:
- `reg_id` (str, optional): 当前规程标识
- `sources` (list[str], optional): 新增来源

##### `load_session() -> SessionState`

加载会话状态。

**返回**: SessionState 对象

---

### QueryAnalyzer

**位置**: `src/regreader/orchestrator/analyzer.py`

查询意图分析器。

#### 主要方法

##### `analyze(query: str, reg_id: str | None = None) -> QueryIntent`

分析查询意图。

**参数**:
- `query` (str): 查询文本
- `reg_id` (str, optional): 规程标识

**返回**: QueryIntent 对象，包含：
- `primary_type`: 主要子代理类型
- `secondary_types`: 次要子代理类型
- `confidence`: 置信度
- `hints`: 提示信息（章节范围、表格提示等）
- `requires_multi_hop`: 是否需要多跳推理

---

## 基础设施层 (Infrastructure Layer)

### FileContext

**位置**: `src/regreader/infrastructure/file_context.py`

文件上下文管理器，实现读写隔离。

#### 初始化

```python
from regreader.infrastructure.file_context import FileContext

ctx = FileContext(
    subagent_name: str,                # 子代理名称
    base_dir: Path,                    # 工作目录
    can_read: list[Path] | None = None,# 可读路径
    can_write: list[Path] | None = None,# 可写路径
    project_root: Path = Path.cwd()    # 项目根目录
)
```

#### 主要方法

##### `read_skill(skill_name: str | None = None) -> str`

读取 SKILL.md 文件。

**参数**:
- `skill_name` (str, optional): 技能名称（默认读取当前子代理的 SKILL.md）

**返回**: 技能内容（Markdown）

##### `read_scratch(filename: str) -> str`

读取临时文件（scratch/）。

**参数**:
- `filename` (str): 文件名

**返回**: 文件内容

##### `write_scratch(filename: str, content: str) -> None`

写入临时文件（scratch/）。

**参数**:
- `filename` (str): 文件名
- `content` (str): 文件内容

##### `read_shared(relative_path: str) -> str`

读取共享资源（shared/）。

**参数**:
- `relative_path` (str): 相对路径

**返回**: 文件内容

##### `log(message: str, level: str = "INFO") -> None`

记录日志到 logs/ 目录。

**参数**:
- `message` (str): 日志消息
- `level` (str): 日志级别

---

### EventBus

**位置**: `src/regreader/infrastructure/event_bus.py`

发布-订阅事件总线。

#### 初始化

```python
from regreader.infrastructure.event_bus import EventBus, SubagentEvent

bus = EventBus(
    event_log_path: Path | None = None # 事件日志路径（JSONL格式）
)
```

#### 事件类型

```python
class SubagentEvent(Enum):
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    HANDOFF_REQUEST = "handoff_request"
    HANDOFF_ACCEPTED = "handoff_accepted"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR_OCCURRED = "error_occurred"
    CONTEXT_SWITCH = "context_switch"
    # ... 14种事件类型
```

#### 主要方法

##### `publish(event_type: SubagentEvent, subagent_id: str, payload: dict[str, Any]) -> None`

发布事件。

**参数**:
- `event_type` (SubagentEvent): 事件类型
- `subagent_id` (str): 子代理标识
- `payload` (dict): 事件负载

**示例**:
```python
bus.publish(
    event_type=SubagentEvent.TASK_STARTED,
    subagent_id="regsearch",
    payload={"query": "母线失压", "reg_id": "angui_2024"}
)
```

##### `subscribe(event_type: SubagentEvent, callback: Callable) -> None`

订阅事件。

**参数**:
- `event_type` (SubagentEvent): 事件类型
- `callback` (Callable): 回调函数

##### `replay_events(since: datetime | None = None) -> list[Event]`

回放历史事件。

**参数**:
- `since` (datetime, optional): 起始时间

**返回**: 事件列表

---

### SkillLoader

**位置**: `src/regreader/infrastructure/skill_loader.py`

技能动态加载器。

#### 初始化

```python
from regreader.infrastructure.skill_loader import SkillLoader

loader = SkillLoader(
    skills_dir: Path | None = None,    # 技能目录，默认 skills/
    registry_path: Path | None = None  # 注册表路径，默认 skills/registry.yaml
)
```

#### 主要方法

##### `load_all() -> dict[str, Skill]`

加载所有技能。

**返回**: 技能字典（技能名 -> Skill对象）

##### `get_skill(name: str) -> Skill | None`

获取单个技能。

**参数**:
- `name` (str): 技能名称

**返回**: Skill 对象或 None

##### `get_skills_for_subagent(subagent_type: str) -> list[Skill]`

获取子代理的所有技能。

**参数**:
- `subagent_type` (str): 子代理类型

**返回**: 技能列表

---

### SecurityGuard

**位置**: `src/regreader/infrastructure/security_guard.py`

安全防护，实现瑞士奶酪防御模型。

#### 初始化

```python
from regreader.infrastructure.security_guard import SecurityGuard

guard = SecurityGuard(
    audit_log_path: Path | None = None # 审计日志路径
)
```

#### 主要方法

##### `check_file_access(subagent_id: str, file_path: Path, mode: str) -> bool`

检查文件访问权限。

**参数**:
- `subagent_id` (str): 子代理标识
- `file_path` (Path): 文件路径
- `mode` (str): 访问模式（"read" 或 "write"）

**返回**: 是否允许访问

##### `check_tool_access(subagent_id: str, tool_name: str) -> bool`

检查工具访问权限。

**参数**:
- `subagent_id` (str): 子代理标识
- `tool_name` (str): 工具名称

**返回**: 是否允许访问

##### `audit_log(subagent_id: str, action: str, details: dict[str, Any]) -> None`

记录审计日志。

**参数**:
- `subagent_id` (str): 子代理标识
- `action` (str): 操作类型
- `details` (dict): 操作详情

---

## 子代理层 (Subagents Layer)

### BaseSubagent

**位置**: `src/regreader/subagents/base.py`

子代理抽象基类（已移除，现在使用配置驱动）。

### RegSearchSubagent

**位置**: `src/regreader/subagents/regsearch/subagent.py`

规程检索专家子代理，整合4个内部组件。

#### 组件

- **SearchAgent**: 文档搜索和导航（4个工具）
- **TableAgent**: 表格搜索和提取（3个工具）
- **ReferenceAgent**: 交叉引用解析（3个工具）
- **DiscoveryAgent**: 语义分析（2个工具，可选）

#### 工具分类

**Phase 0 (BASE)**: 基础检索
- `get_toc`
- `smart_search`
- `read_page_range`

**Phase 1 (MULTI_HOP)**: 多跳推理
- `lookup_annotation`
- `search_tables`
- `resolve_reference`

**Phase 2 (CONTEXT)**: 扩展上下文
- `search_annotations`
- `get_table_by_id`
- `get_block_with_context`

**Phase 3 (DISCOVERY)**: 语义发现
- `find_similar_content`
- `compare_sections`

---

## 使用示例

### 完整检索流程

```python
from regreader.storage import PageStore
from regreader.index import HybridSearch
from regreader.mcp.tools import RegReaderTools

# 初始化组件
store = PageStore()
search = HybridSearch()
tools = RegReaderTools(page_store=store, hybrid_search=search)

# 1. 获取目录
toc = tools.get_toc(reg_id="angui_2024", max_depth=3)

# 2. 执行检索
results = tools.smart_search(
    query="母线失压处理方法",
    reg_id="angui_2024",
    chapter_scope="第六章",
    limit=10
)

# 3. 读取详细内容
if results:
    top_result = results[0]
    content = tools.read_page_range(
        reg_id="angui_2024",
        start_page=top_result["page_num"],
        end_page=top_result["page_num"] + 1
    )
    print(content["markdown_content"])
```

### 使用 Agent 进行对话

```python
# 使用 Pydantic AI Agent
from regreader.agents.pydantic.orchestrator import PydanticOrchestrator

orchestrator = PydanticOrchestrator(reg_id="angui_2024")

# 发送查询
response = await orchestrator.query(
    "母线失压时应该如何处理？请给出具体步骤。"
)

print(response.content)
print(f"来源: {response.sources}")
```

---

## 配置参考

### 环境变量

```bash
# 存储路径
REGREADER_DATA_DIR=./data/storage
REGREADER_PAGES_DIR=./data/storage/pages
REGREADER_INDEX_DIR=./data/storage/index

# 索引后端
REGREADER_KEYWORD_INDEX_BACKEND=fts5      # fts5/tantivy/whoosh
REGREADER_VECTOR_INDEX_BACKEND=lancedb    # lancedb/qdrant

# 检索权重
REGREADER_FTS_WEIGHT=0.4
REGREADER_VECTOR_WEIGHT=0.6
REGREADER_SEARCH_TOP_K=10

# 嵌入模型
REGREADER_EMBEDDING_BACKEND=sentence_transformer
REGREADER_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
REGREADER_EMBEDDING_DIMENSION=512

# LLM配置
REGREADER_LLM_MODEL_NAME=claude-sonnet-4-20250514
REGREADER_LLM_API_KEY=your-api-key
REGREADER_LLM_BASE_URL=https://api.anthropic.com

# MCP服务器
REGREADER_MCP_HOST=127.0.0.1
REGREADER_MCP_PORT=8080
REGREADER_MCP_TRANSPORT=stdio  # stdio/sse
```

---

## 异常处理

RegReader 定义了以下异常层次结构：

```python
RegReaderError (基类)
├── ParserError              # 文档解析错误
├── StorageError             # 存储操作错误
├── IndexError               # 索引操作错误
├── RegulationNotFoundError  # 规程未找到
├── PageNotFoundError        # 页面未找到
├── InvalidPageRangeError    # 页码范围无效
├── ChapterNotFoundError     # 章节未找到
├── AnnotationNotFoundError  # 注释未找到
├── TableNotFoundError       # 表格未找到
└── ReferenceResolutionError # 交叉引用解析错误
```

**使用示例**:
```python
from regreader.exceptions import PageNotFoundError

try:
    page = store.load_page("angui_2024", 999)
except PageNotFoundError as e:
    print(f"页面不存在: {e}")
```

---

## 更多信息

- **架构设计**: 参见 `docs/bash-fs-paradiam/ARCHITECTURE_DESIGN.md`
- **用户指南**: 参见 `docs/bash-fs-paradiam/USER_GUIDE.md`
- **开发文档**: 参见 `docs/dev/DESIGN_DOCUMENT.md`
- **Makefile参考**: 参见 `docs/MAKEFILE_API_REFERENCE.md`
