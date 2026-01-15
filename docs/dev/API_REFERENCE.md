# RegReader API 参考文档

本文档提供 RegReader 项目的完整 API 参考，包括所有公共接口、类和函数的详细说明。

## 目录

- [核心模块 (core)](#核心模块-core)
  - [配置管理 (config)](#配置管理-config)
  - [异常类 (exceptions)](#异常类-exceptions)
- [编排层 (orchestration)](#编排层-orchestration)
- [基础设施层 (infrastructure)](#基础设施层-infrastructure)
- [子代理层 (subagents)](#子代理层-subagents)
- [MCP 工具层 (mcp)](#mcp-工具层-mcp)
- [存储层 (storage)](#存储层-storage)
- [索引层 (index)](#索引层-index)
- [嵌入层 (embedding)](#嵌入层-embedding)

---

## 核心模块 (core)

### 配置管理 (config)

#### `RegReaderSettings`

全局配置类，使用 Pydantic Settings 管理所有配置项。

**继承**: `pydantic_settings.BaseSettings`

**配置来源**:
- 环境变量（前缀 `REGREADER_`）
- `.env` 文件
- 代码中的默认值

**主要配置项**:

##### 存储路径配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `data_dir` | `Path` | `./data/storage` | 数据存储根目录 |
| `pages_dir` | `Path` | `./data/storage/pages` | 页面 JSON 存储目录 |
| `index_dir` | `Path` | `./data/storage/index` | 索引文件目录 |

##### 嵌入模型配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `embedding_backend` | `str` | `sentence_transformer` | 嵌入后端: `sentence_transformer`, `flag` |
| `embedding_model` | `str` | `BAAI/bge-small-zh-v1.5` | HuggingFace 模型名称 |
| `embedding_dimension` | `int` | `512` | 嵌入向量维度 |
| `embedding_device` | `str \| None` | `None` | 运行设备（如 `cuda:0`，默认自动选择） |
| `embedding_local_files_only` | `bool` | `True` | 仅使用本地缓存（离线模式） |

##### LLM 配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `llm_base_url` | `str` | `https://api.anthropic.com` | LLM API 端点 |
| `llm_api_key` | `str` | `""` | LLM API 密钥 |
| `llm_model_name` | `str` | `claude-sonnet-4-20250514` | LLM 模型名称 |
| `ollama_disable_streaming` | `bool` | `False` | Ollama 后端是否禁用流式 |

**注意**: LLM 配置支持 `OPENAI_*` 环境变量别名，兼容 OpenAI SDK。

##### MCP 配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `mcp_host` | `str` | `127.0.0.1` | MCP Server 监听地址 |
| `mcp_port` | `int` | `8080` | MCP Server 监听端口 |
| `use_mcp_mode` | `bool` | `False` | 是否默认使用 MCP 模式 |
| `mcp_transport` | `str` | `stdio` | 传输方式: `stdio`, `sse` |

##### 索引后端配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `keyword_index_backend` | `str` | `fts5` | 关键词索引: `fts5`, `tantivy`, `whoosh` |
| `vector_index_backend` | `str` | `lancedb` | 向量索引: `lancedb`, `qdrant` |
| `search_top_k` | `int` | `10` | 混合检索返回的最大结果数 |
| `fts_weight` | `float` | `0.4` | 关键词检索权重 |
| `vector_weight` | `float` | `0.6` | 语义检索权重 |

**属性方法**:

```python
@property
def fts_db_path(self) -> Path:
    """FTS5 数据库完整路径"""

@property
def lancedb_path(self) -> Path:
    """LanceDB 数据库完整路径"""

def get_llm_provider(self) -> str:
    """根据模型名称推断 LLM 提供商

    Returns:
        提供商名称: anthropic, openai, google
    """

def is_ollama_backend(self) -> bool:
    """检测是否使用 Ollama 后端

    Returns:
        True 如果使用 Ollama 后端
    """
```

**使用示例**:

```python
from regreader.core.config import get_settings

# 获取全局配置实例
settings = get_settings()

# 访问配置项
print(settings.embedding_model)
print(settings.fts_db_path)

# 检测 LLM 提供商
provider = settings.get_llm_provider()
```

#### `get_settings()`

获取全局配置实例（单例模式）。

**返回**: `RegReaderSettings`

#### `reset_settings()`

重置全局配置实例（主要用于测试）。

---

### 异常类 (exceptions)

RegReader 定义了一套完整的异常层次结构，所有自定义异常都继承自 `RegReaderError`。

#### 异常层次结构

```
RegReaderError (基类)
├── ParserError              # 文档解析错误
├── StorageError             # 存储操作错误
├── IndexError               # 索引操作错误
├── RegulationNotFoundError  # 规程不存在
├── PageNotFoundError        # 页面不存在
├── InvalidPageRangeError    # 无效页码范围
├── ChapterNotFoundError     # 章节不存在
├── AnnotationNotFoundError  # 注释不存在
├── TableNotFoundError       # 表格不存在
└── ReferenceResolutionError # 交叉引用解析错误
```

#### `RegReaderError`

所有 RegReader 异常的基类。

**继承**: `Exception`

#### `ParserError`

文档解析过程中发生的错误。

**使用场景**: Docling 解析 PDF/DOCX 失败时抛出。

#### `StorageError`

存储操作失败时抛出的错误。

**使用场景**: 页面数据读写失败、JSON 序列化错误等。

#### `IndexError`

索引操作失败时抛出的错误。

**使用场景**: FTS5/LanceDB 索引构建或查询失败。

#### `RegulationNotFoundError`

指定的规程不存在。

**参数**:
- `reg_id` (str): 规程 ID

**属性**:
- `reg_id` (str): 规程 ID

**示例**:
```python
raise RegulationNotFoundError("angui_2024")
# 错误消息: "规程 'angui_2024' 不存在"
```

#### `PageNotFoundError`

指定的页面不存在。

**参数**:
- `reg_id` (str): 规程 ID
- `page_num` (int): 页码

**属性**:
- `reg_id` (str): 规程 ID
- `page_num` (int): 页码

**示例**:
```python
raise PageNotFoundError("angui_2024", 999)
# 错误消息: "规程 'angui_2024' 的页面 999 不存在"
```

#### `InvalidPageRangeError`

页码范围无效（如起始页大于结束页）。

**参数**:
- `start_page` (int): 起始页码
- `end_page` (int): 结束页码

**属性**:
- `start_page` (int): 起始页码
- `end_page` (int): 结束页码

#### `ChapterNotFoundError`

指定的章节不存在。

**参数**:
- `reg_id` (str): 规程 ID
- `section_number` (str): 章节编号（如 "2.1.4.1.6"）

**属性**:
- `reg_id` (str): 规程 ID
- `section_number` (str): 章节编号

#### `AnnotationNotFoundError`

指定的注释不存在。

**参数**:
- `reg_id` (str): 规程 ID
- `annotation_id` (str): 注释 ID（如 "注1"）

**属性**:
- `reg_id` (str): 规程 ID
- `annotation_id` (str): 注释 ID

#### `TableNotFoundError`

指定的表格不存在。

**参数**:
- `reg_id` (str): 规程 ID
- `table_id` (str): 表格 ID

**属性**:
- `reg_id` (str): 规程 ID
- `table_id` (str): 表格 ID

#### `ReferenceResolutionError`

交叉引用解析失败。

**参数**:
- `reference_text` (str): 引用文本（如 "见第六章"）
- `reason` (str): 失败原因

**属性**:
- `reference_text` (str): 引用文本
- `reason` (str): 失败原因

**示例**:
```python
raise ReferenceResolutionError("见第六章", "章节编号格式不正确")
# 错误消息: "无法解析引用 '见第六章': 章节编号格式不正确"
```

---

## 编排层 (orchestration)

编排层负责查询分析、子代理协调和结果聚合。该层实现了 Bash+FS 范式的文件系统功能。

### 核心组件

| 组件 | 职责 | 文件 |
|------|------|------|
| `Coordinator` | 文件系统任务跟踪（plan.md, session_state.json） | `coordinator.py` |
| `QueryAnalyzer` | 查询意图分析和提示提取 | `analyzer.py` |
| `ResultAggregator` | 多子代理结果聚合 | `aggregator.py` |

### 工作流程

1. **QueryAnalyzer** 从查询中提取提示（chapter_scope, table_hint 等）
2. **Coordinator** 将查询和提示记录到 plan.md（可选）
3. **框架层**（Claude SDK/Pydantic AI/LangGraph）使用 LLM 自主选择子代理
4. **ResultAggregator** 将结果合并为统一响应
5. **Coordinator** 记录结果并更新会话状态（可选）

**注意**: SubagentRouter 已移除，子代理选择现在由框架的原生 LLM 路由机制处理。

### Coordinator

协调器类，负责文件系统任务跟踪和事件记录。

#### `SessionState`

会话状态数据类，持久化到 `coordinator/session_state.json`。

**字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | `str` | 会话唯一标识 |
| `started_at` | `datetime` | 会话开始时间 |
| `query_count` | `int` | 查询计数 |
| `current_reg_id` | `str \| None` | 当前规程标识 |
| `last_query` | `str \| None` | 最后一次查询 |
| `last_hints` | `dict[str, Any] \| None` | 最后一次提取的提示 |
| `accumulated_sources` | `list[str]` | 累积的来源（跨查询） |

**方法**:

```python
def to_dict(self) -> dict[str, Any]:
    """转换为字典"""

@classmethod
def from_dict(cls, data: dict[str, Any]) -> "SessionState":
    """从字典创建"""
```

#### `Coordinator`

协调器类（简化版），仅负责文件系统功能和事件记录。

**参数**:
- `work_dir` (Path | None): 工作目录（默认 `coordinator/`）
- `event_bus` (EventBus | None): 事件总线（可选）

**属性**:
- `work_dir` (Path): 协调器工作目录
- `event_bus` (EventBus | None): 事件总线
- `session_state` (SessionState): 会话状态

**主要方法**:

```python
async def log_query(
    self,
    query: str,
    hints: dict[str, Any],
    reg_id: str | None = None
) -> None:
    """记录查询到 plan.md

    Args:
        query: 用户查询
        hints: 提取的提示
        reg_id: 规程 ID
    """

async def write_result(
    self,
    content: str,
    sources: list[str],
    tool_calls: list[dict[str, Any]]
) -> None:
    """记录结果到 plan.md

    Args:
        content: 结果内容
        sources: 来源列表
        tool_calls: 工具调用记录
    """

def load_session_state(self) -> SessionState:
    """从文件加载会话状态"""

def save_session_state(self) -> None:
    """保存会话状态到文件"""
```

**使用示例**:

```python
from regreader.orchestration import Coordinator

# 创建协调器
coordinator = Coordinator()

# 记录查询
await coordinator.log_query(
    query="母线失压如何处理?",
    hints={"chapter_scope": "第六章"},
    reg_id="angui_2024"
)

# 记录结果
await coordinator.write_result(
    content="处理步骤...",
    sources=["angui_2024:45", "angui_2024:46"],
    tool_calls=[{"tool": "smart_search", "args": {...}}]
)
```

---

### QueryAnalyzer

查询提示提取器，从用户查询中提取结构化提示信息。

#### 提取的提示类型

| 提示类型 | 说明 | 示例 |
|---------|------|------|
| `chapter_scope` | 章节范围 | "第六章" |
| `table_hint` | 表格标识 | "表6-2" |
| `annotation_hint` | 注释标识 | "注1" |
| `scheme_hint` | 方案标识 | "方案A" |
| `reference_text` | 引用文本 | "见第六章" |
| `section_number` | 章节编号 | "2.1.4.1.6" |
| `reg_id` | 规程标识 | "angui_2024" |

#### 主要方法

```python
async def extract_hints(self, query: str) -> dict[str, Any]:
    """提取查询中的提示信息（异步版本）

    Args:
        query: 用户查询

    Returns:
        提示信息字典
    """
```

**使用示例**:

```python
from regreader.orchestration import QueryAnalyzer

analyzer = QueryAnalyzer()

# 提取提示
hints = await analyzer.extract_hints("第六章中表6-2的注1是什么?")
# 返回: {
#     "chapter_scope": "第六章",
#     "table_hint": "表6-2",
#     "annotation_hint": "注1"
# }
```

---

### ResultAggregator

结果聚合器，聚合多个子代理的结果生成最终响应。

#### 聚合策略

1. **内容合并**: 按子代理类型组织内容
2. **来源去重**: 合并所有来源并去重
3. **工具调用合并**: 汇总所有工具调用记录

#### 主要方法

```python
def aggregate(
    self,
    results: list[SubagentResult],
    original_query: str | None = None
) -> AggregatedResult:
    """聚合子代理结果

    Args:
        results: 子代理结果列表
        original_query: 原始用户查询（可选）

    Returns:
        AggregatedResult 聚合结果
    """
```

**使用示例**:

```python
from regreader.orchestration import ResultAggregator

aggregator = ResultAggregator(include_agent_labels=True)

# 聚合结果
result = aggregator.aggregate(
    results=[result1, result2],
    original_query="母线失压如何处理?"
)
```

---

## 基础设施层 (infrastructure)

基础设施层提供 Bash+FS 范式所需的核心组件，支持文件系统通信和安全隔离。

### 核心组件

| 组件 | 职责 | 文件 |
|------|------|------|
| `FileContext` | 文件上下文管理器，实现读写隔离 | `file_context.py` |
| `SkillLoader` | 技能加载器，动态加载 SKILL.md 定义 | `skill_loader.py` |
| `EventBus` | 事件总线，支持子代理间松耦合通信 | `event_bus.py` |
| `SecurityGuard` | 安全守卫，实现目录隔离和权限控制 | `security_guard.py` |

### FileContext

文件上下文管理器，提供读写隔离的文件访问接口。

**主要方法**:

```python
def read_skill(self, skill_name: str) -> str:
    """读取技能文档"""

def read_scratch(self, filename: str) -> str:
    """读取临时文件"""

def write_scratch(self, filename: str, content: str) -> None:
    """写入临时文件"""

def read_shared(self, path: str) -> str:
    """读取共享资源（只读）"""

def log(self, message: str, level: str = "INFO") -> None:
    """写入日志"""
```

**使用示例**:

```python
from regreader.infrastructure import FileContext

ctx = FileContext(workspace_dir="subagents/regsearch")

# 读取技能文档
skill_doc = ctx.read_skill("simple_search")

# 写入临时结果
ctx.write_scratch("results.json", json.dumps(data))

# 读取共享数据
toc = ctx.read_shared("data/angui_2024/toc.json")
```

### SkillLoader

技能加载器，动态加载 SKILL.md 定义。

**主要方法**:

```python
def load_all(self) -> dict[str, Skill]:
    """加载所有技能"""

def get_skill(self, skill_name: str) -> Skill | None:
    """获取指定技能"""

def get_skills_for_subagent(self, subagent_type: str) -> list[Skill]:
    """获取子代理的所有技能"""
```

### EventBus

事件总线，支持子代理间松耦合通信，支持 JSONL 持久化。

**事件类型**: 14 种事件类型（TASK_STARTED, TASK_COMPLETED, HANDOFF_REQUEST 等）

**主要方法**:

```python
async def publish(self, event: Event) -> None:
    """发布事件"""

def subscribe(self, event_type: SubagentEvent, handler: Callable) -> None:
    """订阅事件"""

async def replay_events(self, since: datetime | None = None) -> list[Event]:
    """重放历史事件"""
```

### SecurityGuard

安全守卫，实现瑞士奶酪防御模型（3 层防御）。

**防御层次**:
1. 目录隔离
2. 工具控制
3. 审计日志

**主要方法**:

```python
def check_file_access(self, subagent_id: str, file_path: Path, mode: str) -> bool:
    """检查文件访问权限"""

def check_tool_access(self, subagent_id: str, tool_name: str) -> bool:
    """检查工具访问权限"""

def audit_log(self, subagent_id: str, action: str, details: dict) -> None:
    """记录审计日志"""
```

---

## 存储层 (storage)

存储层提供页面级数据模型和持久化接口。

### 核心数据模型

| 模型 | 说明 |
|------|------|
| `PageDocument` | 单页文档（核心存储单元） |
| `ContentBlock` | 内容块（text/table/heading/list） |
| `TableMeta` | 表格元数据（跨页标记、单元格） |
| `Annotation` | 页面注释（注1、方案A 等） |
| `TocTree` / `TocItem` | 目录树结构 |
| `SearchResult` | 搜索结果（带评分和来源） |

### PageStore

页面存储类，提供页面数据的 CRUD 操作。

**主要方法**:

```python
def save_page(self, page: PageDocument) -> None:
    """保存页面"""

def get_page(self, reg_id: str, page_num: int) -> PageDocument | None:
    """获取单页"""

def get_page_range(self, reg_id: str, start: int, end: int) -> list[PageDocument]:
    """获取页面范围"""

def list_regulations(self) -> list[str]:
    """列出所有规程"""

def delete_regulation(self, reg_id: str) -> None:
    """删除规程"""
```

**使用示例**:

```python
from regreader.storage import PageStore, PageDocument

store = PageStore()

# 保存页面
page = PageDocument(reg_id="angui_2024", page_num=1, ...)
store.save_page(page)

# 获取页面
page = store.get_page("angui_2024", 1)

# 获取页面范围
pages = store.get_page_range("angui_2024", 1, 10)
```

---

## MCP 工具层 (mcp)

MCP 工具层提供 16+ 工具，按阶段分类（BASE/MULTI_HOP/CONTEXT/DISCOVERY）。

### 工具分类

| 阶段 | 工具数量 | 主要工具 |
|------|---------|---------|
| BASE (Phase 0) | 3 | `get_toc`, `smart_search`, `read_page_range` |
| MULTI_HOP (Phase 1) | 3 | `lookup_annotation`, `search_tables`, `resolve_reference` |
| CONTEXT (Phase 2) | 3 | `search_annotations`, `get_table_by_id`, `get_block_with_context` |
| DISCOVERY (Phase 3) | 2 | `find_similar_content`, `compare_sections` |
| NAVIGATION | 3 | `get_tool_guide`, `get_chapter_structure`, `read_chapter_content` |

### 核心工具示例

#### `smart_search`

智能搜索工具，支持混合检索（关键词 + 语义）。

**参数**:
- `query` (str): 搜索查询
- `reg_id` (str): 规程 ID
- `chapter_scope` (str | None): 章节范围
- `limit` (int): 返回结果数量
- `block_types` (list[str] | None): 内容块类型过滤

**返回**: `list[SearchResult]`

#### `read_page_range`

读取页面范围。

**参数**:
- `reg_id` (str): 规程 ID
- `start_page` (int): 起始页码
- `end_page` (int): 结束页码

**返回**: `PageContent`

#### `search_tables`

表格搜索工具。

**参数**:
- `query` (str): 搜索查询
- `reg_id` (str): 规程 ID
- `mode` (str): 搜索模式（keyword/semantic/hybrid）
- `limit` (int): 返回结果数量

**返回**: `list[TableSearchResult]`

---

## 使用指南

### 快速开始

```python
from regreader.core.config import get_settings
from regreader.storage import PageStore
from regreader.mcp.client import MCPClient

# 1. 获取配置
settings = get_settings()

# 2. 初始化存储
store = PageStore()

# 3. 使用 MCP 客户端（可选）
async with MCPClient() as client:
    result = await client.call_tool("smart_search", {
        "query": "母线失压",
        "reg_id": "angui_2024"
    })
```

### 架构层次调用示例

```python
# 编排层使用
from regreader.orchestration import Coordinator, QueryAnalyzer

coordinator = Coordinator()
analyzer = QueryAnalyzer()

hints = await analyzer.extract_hints("第六章中表6-2的注1是什么?")
await coordinator.log_query(query, hints, reg_id="angui_2024")

# 基础设施层使用
from regreader.infrastructure import FileContext, EventBus

ctx = FileContext(workspace_dir="subagents/regsearch")
event_bus = EventBus()

# 存储层使用
from regreader.storage import PageStore

store = PageStore()
page = store.get_page("angui_2024", 1)
```

### 配置最佳实践

```bash
# 环境变量配置
export REGREADER_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
export REGREADER_LLM_MODEL_NAME=claude-sonnet-4-20250514
export REGREADER_KEYWORD_INDEX_BACKEND=fts5
export REGREADER_VECTOR_INDEX_BACKEND=lancedb
```

---

## 附录

### 完整模块列表

- **core**: 配置管理、异常类
- **orchestration**: 协调器、查询分析、结果聚合
- **infrastructure**: 文件上下文、技能加载、事件总线、安全守卫
- **storage**: 页面存储、数据模型
- **mcp**: MCP 服务器、工具定义
- **index**: 混合检索（FTS5/LanceDB/Tantivy/Qdrant）
- **embedding**: 嵌入模型（SentenceTransformer/FlagEmbedding）
- **parser**: Docling 文档解析
- **agents**: 三框架实现（Claude SDK/Pydantic AI/LangGraph）
- **subagents**: 子代理实现（RegSearch 等）

### 相关文档

- [项目 README](../../README.md)
- [Bash+FS 架构设计](../bash-fs-paradiam/ARCHITECTURE_DESIGN.md)
- [子代理架构](../subagents/SUBAGENTS_ARCHITECTURE.md)
- [MCP 工具设计](MCP_TOOLS_DESIGN.md)

---

**文档版本**: v1.0
**最后更新**: 2026-01-15
**维护者**: RegReader 开发团队

