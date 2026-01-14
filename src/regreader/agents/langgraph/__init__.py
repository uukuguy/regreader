"""LangGraph Subagents 实现

基于 LangGraph StateGraph 的 Subagents 协调器实现。
使用原生的子图组合模式:
- 子图作为父图节点，通过 subgraph.invoke() 调用
- 状态转换在节点函数中完成
"""

from regreader.agents.langgraph.orchestrator import (
    LangGraphOrchestrator,
    OrchestratorState,
)
from regreader.agents.langgraph.subgraphs import (
    # 新的构建器 API
    SubgraphBuilder,
    SubgraphOutput,
    SubgraphState,
    create_subgraph_builder,
    # Legacy 类（向后兼容）
    BaseSubgraph,
    DiscoverySubgraph,
    ReferenceSubgraph,
    SearchSubgraph,
    TableSubgraph,
)

__all__ = [
    # Orchestrator
    "LangGraphOrchestrator",
    "OrchestratorState",
    # Subgraph Builder API
    "SubgraphBuilder",
    "SubgraphState",
    "SubgraphOutput",
    "create_subgraph_builder",
    # Legacy (backward compatibility)
    "BaseSubgraph",
    "SearchSubgraph",
    "TableSubgraph",
    "ReferenceSubgraph",
    "DiscoverySubgraph",
]
