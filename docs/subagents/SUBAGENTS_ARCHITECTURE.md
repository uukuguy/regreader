# Subagents 架构设计文档

## 1. 概述

Subagents 架构将单一的 GridCode Agent 分解为多个专业化的子代理（Subagent），每个子代理拥有独立的上下文和工具集，通过 Orchestrator 协调实现复杂查询的分解和执行。

### 1.1 设计目标

- **上下文隔离**: 减轻主 Agent 的上下文压力，从 ~4000 tokens 降至 ~800 tokens
- **专业化处理**: 每个 Subagent 专注于特定领域（搜索、表格、引用等）
- **框架统一**: 三个框架（Claude/Pydantic/LangGraph）共享相同的 Subagent 定义
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
src/grid_code/
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
│   │   ├── orchestrator.py       # PydanticOrchestrator
│   │   └── subagents.py          # Pydantic Subagent 实现
│   │
│   └── langgraph/                # LangGraph 实现
│       ├── __init__.py
│       ├── orchestrator.py       # LangGraphOrchestrator
│       └── subgraphs.py          # Subgraph 实现
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

### 5.2 Pydantic AI

**模式**: Dependent Agents（依赖代理）

**特点**:
- Subagents 作为 tools 注册到 Orchestrator
- 创建过滤的 `MCPServerStdio`，仅暴露指定工具
- 通过 `register_tool` 动态注册

**关键代码**:
```python
class BasePydanticSubagent(BaseSubagent):
    def _get_allowed_tools(self) -> list[str]:
        return [get_tool_name(name) for name in self.config.tools]

    async def execute(self, context: SubagentContext) -> SubagentResult:
        allowed_tools = self._get_allowed_tools()
        async with self._mcp_manager.get_connection(allowed_tools) as server:
            agent = Agent(model=self._model, mcp_servers=[server], ...)
            result = await agent.run(context.query)
```

### 5.3 LangGraph

**模式**: Subgraphs（子图）

**特点**:
- 每个 Subagent 是独立的 `StateGraph`
- `SubgraphState` 与 `OrchestratorState` 分离
- 通过 `compile()` 生成可执行图

**关键代码**:
```python
class BaseLangGraphSubagent(BaseSubagent):
    def _create_graph(self) -> CompiledGraph:
        builder = StateGraph(SubgraphState)
        builder.add_node("agent", self._agent_node)
        builder.add_node("tools", self._tool_node)
        builder.add_edge(START, "agent")
        builder.add_conditional_edges("agent", self._should_continue)
        return builder.compile()
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
gridcode chat -r angui_2024 --orchestrator

# 单次查询 + Orchestrator
gridcode ask "表6-2注1的内容" -r angui_2024 -o

# 指定框架
gridcode chat -r angui_2024 --agent pydantic -o
gridcode chat -r angui_2024 --agent langgraph -o
```

### 7.2 编程接口

```python
from grid_code.agents import ClaudeOrchestrator

async with ClaudeOrchestrator(reg_id="angui_2024") as orchestrator:
    response = await orchestrator.chat("表6-2中注1的内容是什么？")
    print(response.content)
```

## 8. 配置选项

```python
# 在 src/grid_code/config.py 中

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

## 11. 测试

```bash
# 单元测试
pytest tests/subagents/ -xvs
pytest tests/orchestrator/ -xvs

# 集成测试
pytest tests/agents/test_orchestrator_integration.py -xvs
```
