# Subagents 架构设计文档

## 1. 概述

Subagents 架构将单一的 RegReader Agent 分解为多个专业化的子代理（Subagent），每个子代理拥有独立的上下文和工具集，通过 Orchestrator 协调实现复杂查询的分解和执行。

### 1.1 设计目标

- **上下文隔离**: 减轻主 Agent 的上下文压力，从 ~4000 tokens 降至 ~800 tokens
- **专业化处理**: 每个 Subagent 专注于特定领域（搜索、表格、引用等）
- **框架统一**: 三个框架（Claude/Pydantic/LangGraph）共享相同的 Subagent 定义
- **原生模式**: 每个框架使用其原生的子代理/委托模式
- **可扩展性**: 易于添加新的 Subagent 类型

### 1.2 架构对比

**重构前**:
```
Main Agent (单一)
  └── 10 个工具 + 完整协议 (~4000 tokens)
      └── 上下文随对话快速膨胀
```

**重构后**:
```
Orchestrator (协调器, ~800 tokens)
  ├── 查询意图分析 (QueryAnalyzer)
  ├── Subagent 路由 (SubagentRouter)
  └── 结果聚合 (ResultAggregator)

Subagents (专家代理, 各 ~600 tokens)
  ├── SearchAgent (4 tools): 文档搜索与导航
  ├── TableAgent (3 tools): 表格搜索与提取
  ├── ReferenceAgent (3 tools): 引用解析与追踪
  └── DiscoveryAgent (2 tools): 高级语义分析 [可选]
```

## 2. 目录结构

```
src/regreader/
├── subagents/                    # Subagent 框架（统一定义）
│   ├── __init__.py
│   ├── base.py                   # 抽象基类 (BaseSubagent, SubagentContext)
│   ├── config.py                 # 配置定义 (SubagentConfig, SubagentType)
│   ├── result.py                 # 结果模型 (SubagentResult)
│   ├── registry.py               # 注册表 (SubagentRegistry)
│   └── prompts.py                # 专用提示词 (SUBAGENT_PROMPTS)
│
├── orchestrator/                 # 协调层
│   ├── __init__.py
│   ├── analyzer.py               # 查询意图分析
│   ├── router.py                 # Subagent 路由
│   └── aggregator.py             # 结果聚合
│
├── agents/                       # 框架实现
│   ├── claude/                   # Claude SDK 实现
│   │   ├── __init__.py
│   │   ├── orchestrator.py       # ClaudeOrchestrator
│   │   └── subagents.py          # Claude Subagent 实现
│   │
│   ├── pydantic/                 # Pydantic AI 实现
│   │   ├── __init__.py
│   │   ├── orchestrator.py       # PydanticOrchestrator (使用 @tool 委托)
│   │   └── subagents.py          # SubagentBuilder 实现
│   │
│   └── langgraph/                # LangGraph 实现
│       ├── __init__.py
│       ├── orchestrator.py       # LangGraphOrchestrator (父图)
│       └── subgraphs.py          # SubgraphBuilder 实现
```

## 3. 核心接口

### 3.1 SubagentContext

传递给 Subagent 的执行上下文：

```python
@dataclass
class SubagentContext:
    query: str                              # 原始查询
    reg_id: str | None = None               # 目标规程
    chapter_scope: str | None = None        # 章节范围提示
    hints: dict[str, Any] = field(default_factory=dict)  # 协调器提示
    max_iterations: int = 5                 # 最大迭代次数
```

### 3.2 SubagentConfig

Subagent 的统一配置：

```python
@dataclass
class SubagentConfig:
    agent_type: SubagentType                # 代理类型
    name: str                               # 显示名称
    description: str                        # 描述
    tools: list[str]                        # MCP 工具名列表
    system_prompt: str                      # 专用系统提示词
    capabilities: list[str]                 # 能力关键词（用于路由）
    keywords: list[str]                     # 触发关键词
    priority: int = 2                       # 优先级
    enabled: bool = True                    # 是否启用
    max_iterations: int = 5                 # 最大迭代次数
```

### 3.3 SubagentResult

Subagent 执行结果：

```python
@dataclass
class SubagentResult:
    agent_type: SubagentType                # 代理类型
    success: bool                           # 是否成功
    content: str                            # 提取的内容
    sources: list[str]                      # 来源引用
    tool_calls: list[dict]                  # 工具调用记录
    data: dict[str, Any]                    # 结构化数据
    error: str | None = None                # 错误信息
    confidence: float = 1.0                 # 置信度
```

### 3.4 BaseSubagent

Subagent 抽象基类：

```python
class BaseSubagent(ABC):
    def __init__(self, config: SubagentConfig): ...

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def execute(self, context: SubagentContext) -> SubagentResult: ...

    @abstractmethod
    async def reset(self) -> None: ...
```

## 4. Subagent 分类

### 4.1 SearchAgent

负责文档搜索与导航。

**工具集**:
- `list_regulations`: 列出所有规程
- `get_toc`: 获取目录结构
- `smart_search`: 智能搜索
- `read_page_range`: 读取页面范围

**触发关键词**: 搜索、查找、查询、有哪些、列出、规程、章节、目录

### 4.2 TableAgent

负责表格搜索与提取。

**工具集**:
- `search_tables`: 搜索表格
- `get_table_by_id`: 获取表格详情
- `lookup_annotation`: 查找注释

**触发关键词**: 表格、表、注、注释、选项、说明

### 4.3 ReferenceAgent

负责引用解析与追踪。

**工具集**:
- `resolve_reference`: 解析引用
- `lookup_annotation`: 查找注释
- `read_page_range`: 读取页面

**触发关键词**: 引用、参见、见、参考、条款、附录

### 4.4 DiscoveryAgent

负责高级语义分析（默认禁用）。

**工具集**:
- `find_similar_content`: 查找相似内容
- `compare_sections`: 比较章节

**触发关键词**: 相似、类似、比较、对比、差异

## 5. 框架实现策略

### 5.1 Claude Agent SDK

**模式**: Handoff Pattern（嵌套代理）

**特点**:
- 每个 Subagent 是独立的 `ClaudeSDKClient` 实例
- 通过 `allowed_tools` 参数过滤可用工具
- 上下文完全隔离

**关键代码**:
```python
class BaseClaudeSubagent(BaseSubagent):
    def _get_allowed_tools(self) -> list[str]:
        return [get_tool_name(name) for name in self.config.tools]

    def _build_options(self, context: SubagentContext) -> ClaudeAgentOptions:
        return ClaudeAgentOptions(
            model=self._model,
            allowed_tools=self._get_allowed_tools(),
            system=self._build_system_prompt(context),
        )
```

### 5.2 Pydantic AI（原生委托模式）

**模式**: Agent Delegation（代理委托）

**特点**:
- Orchestrator 通过 `@tool` 装饰器注册委托工具
- 使用 `ctx.deps` 传递共享依赖
- 使用 `ctx.usage` 聚合所有 Subagent 的 token 消耗

**架构图**:
```
OrchestratorAgent (主协调器 Agent)
    ├── @tool call_search_agent(ctx, query) -> 调用 SearchSubagent
    ├── @tool call_table_agent(ctx, query) -> 调用 TableSubagent
    ├── @tool call_reference_agent(ctx, query) -> 调用 ReferenceSubagent
    └── @tool call_discovery_agent(ctx, query) -> 调用 DiscoverySubagent
```

**关键代码**:
```python
# 依赖定义
@dataclass
class OrchestratorDependencies:
    reg_id: str | None = None
    mcp_server: Any = None
    subagent_builders: dict[SubagentType, SubagentBuilder] = field(default_factory=dict)
    subagent_agents: dict[SubagentType, Any] = field(default_factory=dict)
    hints: dict[str, Any] = field(default_factory=dict)

# 注册委托工具
@orchestrator.tool
async def call_search_agent(
    ctx: RunContext[OrchestratorDependencies],
    query: str,
) -> str:
    """调用搜索专家代理"""
    return await _invoke_subagent(ctx, SubagentType.SEARCH, query)

# 调用 Subagent（原生委托模式）
async def _invoke_subagent(ctx, agent_type, query) -> str:
    deps = ctx.deps
    builder = deps.subagent_builders[agent_type]
    subagent = deps.subagent_agents.get(agent_type) or builder.build(deps.mcp_server)

    # 关键：传递 usage 以聚合 token 消耗
    output = await builder.invoke(
        subagent,
        query,
        subagent_deps,
        usage=ctx.usage,  # ← Pydantic AI 原生使用量追踪
    )
    return output.content
```

**SubagentBuilder API**:
```python
class SubagentBuilder:
    """Pydantic AI Subagent 构建器"""

    def __init__(self, config: SubagentConfig, model: str): ...

    def build(self, mcp_server: MCPServerStdio) -> Agent[SubagentDependencies, str]:
        """构建 Agent 实例"""
        ...

    async def invoke(
        self,
        agent: Agent,
        query: str,
        deps: SubagentDependencies,
        usage: Usage | None = None,
    ) -> SubagentOutput:
        """调用 Subagent（传递 usage 以聚合使用量）"""
        ...
```

### 5.3 LangGraph（原生子图模式）

**模式**: Subgraphs（子图组合）

**特点**:
- 父图（Orchestrator）和子图（Subagent）使用独立的 State 定义
- 子图作为父图节点，通过 `builder.invoke()` 调用
- 状态转换在节点函数中完成

**架构图**:
```
OrchestratorGraph (父图 StateGraph)
    ├── router_node (路由节点)
    │       └── QueryAnalyzer 分析意图
    │
    ├── execute_subgraphs_node (执行节点)
    │       └── 调用 SubgraphBuilder.invoke()
    │
    └── aggregator_node (聚合节点)
            └── ResultAggregator 聚合结果

SubgraphBuilder.invoke()
    └── CompiledGraph.ainvoke(SubgraphState)
            ├── agent_node (LLM 调用)
            ├── tools_node (工具执行)
            └── should_continue (条件边)
```

**状态定义**:
```python
# 父图状态
class OrchestratorState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    query: str
    reg_id: str | None
    intent: QueryIntent | None
    selected_subgraphs: list[str]
    subgraph_results: dict[str, SubgraphOutput]
    final_content: str
    all_sources: list[str]
    all_tool_calls: list[dict]

# 子图状态（独立）
class SubgraphState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    query: str
    reg_id: str | None
    hints: dict[str, Any]
```

**SubgraphBuilder API**:
```python
class SubgraphBuilder:
    """LangGraph Subgraph 构建器"""

    def __init__(self, config: SubagentConfig, llm: ChatOpenAI, mcp_client: RegReaderMCPClient): ...

    def build(self) -> CompiledGraph:
        """构建并编译 Subgraph"""
        ...

    async def invoke(
        self,
        query: str,
        reg_id: str | None = None,
        hints: dict[str, Any] | None = None,
    ) -> SubgraphOutput:
        """调用 Subgraph"""
        ...
```

**父图节点实现**:
```python
async def execute_subgraphs_node(state: OrchestratorState) -> dict:
    """执行选中的 Subgraph"""
    results = {}

    for subgraph_name in state["selected_subgraphs"]:
        builder = subgraph_builders[subgraph_name]

        # 调用子图（状态转换在此完成）
        output = await builder.invoke(
            query=state["query"],
            reg_id=state["reg_id"],
            hints=state.get("intent", {}).hints if state.get("intent") else {},
        )

        results[subgraph_name] = output

    return {"subgraph_results": results}
```

## 6. 协调层

### 6.1 QueryAnalyzer

分析用户查询的意图：

```python
@dataclass
class QueryIntent:
    primary_type: SubagentType              # 主要意图
    secondary_types: list[SubagentType]     # 次要意图
    requires_multi_hop: bool                # 是否需要多步推理
    hints: dict[str, Any]                   # 额外提示（如章节范围）
```

### 6.2 SubagentRouter

路由查询到合适的 Subagent：

- 支持顺序执行（sequential）和并行执行（parallel）
- 基于关键词和意图分析选择 Subagent
- 默认回退到 SearchAgent

### 6.3 ResultAggregator

聚合多个 Subagent 的结果：

- 合并内容和来源
- 处理冲突和去重
- 生成统一的响应格式

## 7. 使用方法

### 7.1 CLI

```bash
# 交互模式 + Orchestrator
regreader chat -r angui_2024 --orchestrator

# 单次查询 + Orchestrator
regreader ask "表6-2注1的内容" -r angui_2024 -o

# 指定框架
regreader chat -r angui_2024 --agent pydantic -o
regreader chat -r angui_2024 --agent langgraph -o
```

### 7.2 编程接口

**LangGraph**:
```python
from regreader.agents.langgraph import LangGraphOrchestrator

async with LangGraphOrchestrator(reg_id="angui_2024") as orchestrator:
    response = await orchestrator.chat("表6-2中注1的内容是什么？")
    print(response.content)
```

**Pydantic AI**:
```python
from regreader.agents.pydantic import PydanticOrchestrator

async with PydanticOrchestrator(reg_id="angui_2024") as orchestrator:
    response = await orchestrator.chat("表6-2中注1的内容是什么？")
    print(response.content)
    # 使用量已通过 ctx.usage 自动聚合
```

**Claude SDK**:
```python
from regreader.agents.claude import ClaudeOrchestrator

async with ClaudeOrchestrator(reg_id="angui_2024") as orchestrator:
    response = await orchestrator.chat("表6-2中注1的内容是什么？")
    print(response.content)
```

## 8. 配置选项

```python
# 在 src/regreader/config.py 中

# Subagent 架构配置
enable_orchestrator: bool = False          # 启用 subagent 模式
enabled_subagents: list[str] = ["search", "table", "reference"]
subagent_max_iterations: int = 5           # 每个 subagent 最大迭代
orchestrator_mode: str = "sequential"      # sequential / parallel
```

## 9. 性能考虑

### 9.1 上下文优化

- Orchestrator 提示词：~800 tokens（vs 原 ~4000 tokens）
- 每个 Subagent 提示词：~600 tokens
- 总上下文在多步查询时可能增加，但单步查询效率更高

### 9.2 延迟考虑

- 顺序执行：延迟 = Σ(Subagent 延迟)
- 并行执行：延迟 = max(Subagent 延迟)
- 建议对独立查询使用并行模式

### 9.3 成本考虑

- 每个 Subagent 调用产生独立的 API 请求
- 简单查询可能比单一 Agent 更昂贵
- 复杂查询通过专业化处理可能更高效
- Pydantic AI 通过 `ctx.usage` 自动追踪所有 token 消耗

## 10. 扩展指南

### 10.1 添加新 Subagent

1. 在 `subagents/config.py` 中添加 `SubagentType` 枚举值
2. 创建配置 `XXX_AGENT_CONFIG`
3. 在 `subagents/prompts.py` 中添加专用提示词
4. 为每个框架实现具体的 Subagent 类
5. 在 `SubagentRegistry` 中注册

### 10.2 自定义路由逻辑

继承 `SubagentRouter` 并覆盖 `_select_subagents` 方法：

```python
class CustomRouter(SubagentRouter):
    async def _select_subagents(
        self, intent: QueryIntent
    ) -> list[SubagentType]:
        # 自定义路由逻辑
        ...
```

## 11. 框架对比

| 特性 | Claude SDK | Pydantic AI | LangGraph |
|------|------------|-------------|-----------|
| 模式 | Handoff Pattern | Agent Delegation | Subgraphs |
| 状态隔离 | 独立实例 | deps 传递 | State 分离 |
| 工具过滤 | allowed_tools | prompt 限制 | 独立 MCP Client |
| 使用量追踪 | 手动 | ctx.usage 原生 | 手动 |
| 依赖注入 | - | ctx.deps 原生 | 状态传递 |
| 适用场景 | Anthropic API | 通用 OpenAI 兼容 | 复杂工作流 |

## 12. 测试

```bash
# 单元测试
pytest tests/subagents/ -xvs
pytest tests/orchestrator/ -xvs

# 集成测试
pytest tests/agents/test_orchestrator_integration.py -xvs
```

## 13. 更新历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2025-01-11 | v2.0 | 重构为原生模式：LangGraph 使用子图组合，Pydantic AI 使用 @tool 委托 + deps/usage |
| 2025-01-10 | v1.0 | 初始 Subagents 架构实现 |
