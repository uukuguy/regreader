# Subagents 重构工作日志

## 概述
将 GridCode 重构为 **Subagents 范式**，通过独立上下文减轻主 Agent 的上下文容量压力。

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
- `src/grid_code/subagents/__init__.py` - 模块导出
- `src/grid_code/subagents/base.py` - 抽象基类 (BaseSubagent, SubagentContext)
- `src/grid_code/subagents/config.py` - 配置定义 (SubagentConfig, SubagentType)
- `src/grid_code/subagents/result.py` - 结果模型 (SubagentResult)
- `src/grid_code/subagents/registry.py` - 注册表 (SubagentRegistry)
- `src/grid_code/subagents/prompts.py` - 专用提示词

#### Orchestrator 协调层
- `src/grid_code/orchestrator/__init__.py` - 模块导出
- `src/grid_code/orchestrator/analyzer.py` - QueryAnalyzer（查询意图分析）
- `src/grid_code/orchestrator/router.py` - SubagentRouter（路由逻辑）
- `src/grid_code/orchestrator/aggregator.py` - ResultAggregator（结果聚合）

#### LangGraph 实现
- `src/grid_code/agents/langgraph/__init__.py` - 模块导出
- `src/grid_code/agents/langgraph/orchestrator.py` - LangGraphOrchestrator
- `src/grid_code/agents/langgraph/subgraphs.py` - Subgraph 实现

#### Pydantic AI 实现
- `src/grid_code/agents/pydantic/__init__.py` - 模块导出
- `src/grid_code/agents/pydantic/orchestrator.py` - PydanticOrchestrator
- `src/grid_code/agents/pydantic/subagents.py` - Pydantic Subagent 实现

#### Claude Agent SDK 实现
- `src/grid_code/agents/claude/__init__.py` - 模块导出
- `src/grid_code/agents/claude/orchestrator.py` - ClaudeOrchestrator
- `src/grid_code/agents/claude/subagents.py` - Claude Subagent 实现

### 修改文件

#### Agents 模块
- `src/grid_code/agents/__init__.py` - 添加三个 Orchestrator 的导出

#### CLI
- `src/grid_code/cli.py` - 添加 `--orchestrator` 标志到 `chat` 和 `ask` 命令

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
gridcode chat -r angui_2024 --orchestrator
gridcode chat -r angui_2024 -o  # 简写

# 单次查询 + Orchestrator
gridcode ask "表6-2注1的内容" -r angui_2024 --orchestrator
gridcode ask "表6-2注1的内容" -r angui_2024 -o  # 简写

# 指定框架 + Orchestrator
gridcode chat -r angui_2024 --agent pydantic -o
gridcode chat -r angui_2024 --agent langgraph -o
```

### 验证结果

所有导入验证通过：
```python
from grid_code.agents import (
    ClaudeOrchestrator,
    PydanticOrchestrator,
    LangGraphOrchestrator
)
```

CLI 帮助显示正确：
- `gridcode chat --help` 显示 `--orchestrator` 选项
- `gridcode ask --help` 显示 `--orchestrator` 选项

### 后续优化方向

1. **并行执行优化**: 当前默认为顺序执行，可以根据查询类型启用并行执行
2. **缓存机制**: 对于重复查询可以缓存 Subagent 结果
3. **动态工具选择**: 根据历史执行结果动态调整工具权重
4. **监控与调试**: 添加更详细的执行日志和性能指标
