# Subagents 重构工作日志

## 概述
将 RegReader 重构为 **Subagents 范式**，通过独立上下文减轻主 Agent 的上下文容量压力。

## 2025-01-10 工作记录

### 完成进度

| Phase | 任务 | 状态 |
|-------|------|------|
| Phase 1 | 创建 subagents 基础抽象层 | ✅ 完成 |
| Phase 2 | 创建 orchestrator 协调层 | ✅ 完成 |
| Phase 3 | 实现 LangGraph orchestrator | ✅ 完成 |
| Phase 4 | 实现 Pydantic AI orchestrator | ✅ 完成 |
| Phase 5 | 实现 Claude Agent SDK orchestrator | ✅ 完成 |
| Phase 6 | 集成与迁移（CLI、配置、文档） | ✅ 完成 |

### 新增文件

#### Subagents 基础层
- `src/regreader/subagents/__init__.py` - 模块导出
- `src/regreader/subagents/base.py` - 抽象基类 (BaseSubagent, SubagentContext)
- `src/regreader/subagents/config.py` - 配置定义 (SubagentConfig, SubagentType)
- `src/regreader/subagents/result.py` - 结果模型 (SubagentResult)
- `src/regreader/subagents/registry.py` - 注册表 (SubagentRegistry)
- `src/regreader/subagents/prompts.py` - 专用提示词

#### Orchestrator 协调层
- `src/regreader/orchestrator/__init__.py` - 模块导出
- `src/regreader/orchestrator/analyzer.py` - QueryAnalyzer（查询意图分析）
- `src/regreader/orchestrator/router.py` - SubagentRouter（路由逻辑）
- `src/regreader/orchestrator/aggregator.py` - ResultAggregator（结果聚合）

#### LangGraph 实现
- `src/regreader/agents/langgraph/__init__.py` - 模块导出
- `src/regreader/agents/langgraph/orchestrator.py` - LangGraphOrchestrator
- `src/regreader/agents/langgraph/subgraphs.py` - Subgraph 实现

#### Pydantic AI 实现
- `src/regreader/agents/pydantic/__init__.py` - 模块导出
- `src/regreader/agents/pydantic/orchestrator.py` - PydanticOrchestrator
- `src/regreader/agents/pydantic/subagents.py` - Pydantic Subagent 实现

#### Claude Agent SDK 实现
- `src/regreader/agents/claude/__init__.py` - 模块导出
- `src/regreader/agents/claude/orchestrator.py` - ClaudeOrchestrator
- `src/regreader/agents/claude/subagents.py` - Claude Subagent 实现

### 修改文件

#### Agents 模块
- `src/regreader/agents/__init__.py` - 添加三个 Orchestrator 的导出

#### CLI
- `src/regreader/cli.py` - 添加 `--orchestrator` 标志到 `chat` 和 `ask` 命令

### 技术实现细节

#### 三框架不同的实现模式

| 框架 | 模式 | 特点 |
|------|------|------|
| Claude Agent SDK | Handoff Pattern | 每个 Subagent 是独立的 ClaudeSDKClient 实例，通过 `allowed_tools` 过滤工具 |
| Pydantic AI | Dependent Agents | Subagents 作为 tools 注册到 Orchestrator，通过过滤的 MCPServerStdio 暴露工具 |
| LangGraph | Subgraphs | 每个 Subagent 是独立的 StateGraph，状态隔离 |

#### Subagent 分类

| Subagent | 工具 | 职责 |
|----------|------|------|
| SearchAgent | `list_regulations`, `get_toc`, `smart_search`, `read_page_range` | 规程发现、目录导航、内容搜索 |
| TableAgent | `search_tables`, `get_table_by_id`, `lookup_annotation` | 表格搜索、跨页合并、注释追踪 |
| ReferenceAgent | `resolve_reference`, `lookup_annotation`, `read_page_range` | 交叉引用解析、引用内容提取 |
| DiscoveryAgent | `find_similar_content`, `compare_sections` | 相似内容发现、章节比较 [默认禁用] |

### CLI 使用方法

```bash
# 交互模式 + Orchestrator
regreader chat -r angui_2024 --orchestrator
regreader chat -r angui_2024 -o  # 简写

# 单次查询 + Orchestrator
regreader ask "表6-2注1的内容" -r angui_2024 --orchestrator
regreader ask "表6-2注1的内容" -r angui_2024 -o  # 简写

# 指定框架 + Orchestrator
regreader chat -r angui_2024 --agent pydantic -o
regreader chat -r angui_2024 --agent langgraph -o
```

### 验证结果

所有导入验证通过：
```python
from regreader.agents import (
    ClaudeOrchestrator,
    PydanticOrchestrator,
    LangGraphOrchestrator
)
```

CLI 帮助显示正确：
- `regreader chat --help` 显示 `--orchestrator` 选项
- `regreader ask --help` 显示 `--orchestrator` 选项

### 后续优化方向

1. **并行执行优化**: 当前默认为顺序执行，可以根据查询类型启用并行执行
2. **缓存机制**: 对于重复查询可以缓存 Subagent 结果
3. **动态工具选择**: 根据历史执行结果动态调整工具权重
4. **监控与调试**: 添加更详细的执行日志和性能指标

---

## 2025-01-11 工作记录

### 任务目标

验证并重构 LangGraph 和 Pydantic AI 的 Subagent 实现，确保使用各框架的原生模式：
- **LangGraph**: 使用 Subgraphs（子图组合）模式
- **Pydantic AI**: 使用委托（@tool）和依赖注入（deps/usage）模式

### 问题分析

通过 Context7 查询官方文档，发现原有实现存在以下偏差：

#### Pydantic AI 问题
- 使用 `FilteredMCPToolset` workaround 过滤工具
- 未使用原生的 `@tool` 装饰器委托模式
- 未利用 `ctx.deps` 依赖注入和 `ctx.usage` 使用量追踪

#### LangGraph 问题（前一会话已修复）
- 手动状态管理，未使用子图作为父图节点
- 状态转换逻辑复杂，缺少父子状态隔离

### 重构内容

#### 1. Pydantic AI 原生委托模式重构

**`src/regreader/agents/pydantic/subagents.py`** - 完全重写

新增核心类：
```python
@dataclass
class SubagentDependencies:
    """Subagent 共享依赖，通过 ctx.deps 传递"""
    reg_id: str | None = None
    mcp_server: Any = None
    hints: dict[str, Any] = field(default_factory=dict)

@dataclass
class SubagentOutput:
    """Subagent 输出结果"""
    content: str
    sources: list[str] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    success: bool = True
    error: str | None = None

class SubagentBuilder:
    """Pydantic AI Subagent 构建器"""
    def build(self, mcp_server: MCPServerStdio) -> Agent[SubagentDependencies, str]: ...
    async def invoke(self, agent, query, deps, usage=None) -> SubagentOutput: ...
```

**`src/regreader/agents/pydantic/orchestrator.py`** - 完全重写

原生委托模式实现：
```python
@dataclass
class OrchestratorDependencies:
    """Orchestrator 依赖"""
    reg_id: str | None = None
    mcp_server: Any = None
    subagent_builders: dict[SubagentType, SubagentBuilder] = field(default_factory=dict)
    subagent_agents: dict[SubagentType, Any] = field(default_factory=dict)
    hints: dict[str, Any] = field(default_factory=dict)

# @tool 装饰器注册委托工具
@orchestrator.tool
async def call_search_agent(ctx: RunContext[OrchestratorDependencies], query: str) -> str:
    """委托给搜索专家处理"""
    return await _invoke_subagent(ctx, SubagentType.SEARCH, query)

# 使用量聚合
async def _invoke_subagent(ctx, agent_type, query) -> str:
    output = await builder.invoke(subagent, query, subagent_deps, usage=ctx.usage)
    return output.content
```

#### 2. LangGraph 原生子图模式（前一会话已完成）

**`src/regreader/agents/langgraph/subgraphs.py`** - 状态隔离
```python
class SubgraphState(TypedDict):
    """子图独立状态"""
    query: str
    reg_id: str
    output: SubgraphOutput

class SubgraphBuilder:
    def build(self) -> CompiledGraph: ...
```

**`src/regreader/agents/langgraph/orchestrator.py`** - 父图组合
```python
class OrchestratorState(TypedDict):
    """父图状态"""
    query: str
    reg_id: str
    subgraph_outputs: dict[str, SubgraphOutput]
    final_answer: str

# 子图作为父图节点
def _create_subgraph_node(self, builder: SubgraphBuilder):
    async def node(state: OrchestratorState) -> dict:
        subgraph_state = SubgraphState(query=state["query"], reg_id=state["reg_id"])
        result = await subgraph.ainvoke(subgraph_state)
        return {"subgraph_outputs": {builder.name: result["output"]}}
    return node
```

### 修改文件列表

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `src/regreader/agents/pydantic/subagents.py` | 重写 | 新增 SubagentBuilder，保留 Legacy 类向后兼容 |
| `src/regreader/agents/pydantic/orchestrator.py` | 重写 | 使用 @tool 委托模式 + deps/usage 传递 |
| `src/regreader/agents/pydantic/__init__.py` | 更新 | 导出新 API + Legacy 类 |
| `src/regreader/agents/langgraph/__init__.py` | 更新 | 导出新 API + Legacy 类 |
| `docs/subagents/SUBAGENTS_ARCHITECTURE.md` | 更新 | 新增 5.2/5.3 原生模式说明、框架对比表、更新历史 |

### 验证结果

导入验证通过：
```bash
python -c "from regreader.agents.pydantic import SubagentBuilder, PydanticOrchestrator; print('OK')"
python -c "from regreader.agents.langgraph import SubgraphBuilder, LangGraphOrchestrator; print('OK')"
```

### 框架对比总结

| 特性 | Pydantic AI | LangGraph |
|------|-------------|-----------|
| 子代理模式 | @tool 委托 | 子图组合 |
| 依赖注入 | ctx.deps | state 传递 |
| 使用量追踪 | ctx.usage 自动聚合 | 手动管理 |
| 状态隔离 | Agent 实例隔离 | TypedDict 类型隔离 |
| 工具限制 | system prompt 指示 | 子图独立工具集 |

### 后续优化方向

1. **运行时验证**: 在实际 MCP Server 环境中验证完整流程
2. **性能测试**: 对比重构前后的响应延迟和 token 消耗
3. **错误处理增强**: 添加子代理调用失败的重试和降级机制
4. **监控集成**: 添加 OpenTelemetry span 追踪子代理调用链
