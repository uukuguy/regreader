"""GridCode Orchestrator Module

协调层，负责查询分析、Subagent 路由和结果聚合。

This module provides the coordination layer that analyzes user queries,
routes them to appropriate subagents, and aggregates the results.

Key Components:
    Coordinator: Central dispatch for query processing (file-based task dispatch).
    QueryAnalyzer: Analyzes user queries to determine intent and extract hints.
    QueryIntent: Result of query analysis (primary/secondary types, hints).
    SubagentRouter: Routes queries to appropriate subagents and executes them.
    ResultAggregator: Aggregates results from multiple subagents.

Workflow:
    1. Coordinator receives user query
    2. QueryAnalyzer analyzes the query intent
    3. SubagentRouter selects and executes appropriate subagents
    4. ResultAggregator combines the results into a unified response
    5. Coordinator publishes events and updates session state

Example:
    >>> from grid_code.orchestrator import Coordinator
    >>> from grid_code.subagents import SubagentType
    >>> coordinator = Coordinator(subagents={...})
    >>> result = await coordinator.process_query("母线失压如何处理?", reg_id="angui_2024")
"""

from grid_code.orchestrator.aggregator import ResultAggregator
from grid_code.orchestrator.analyzer import QueryAnalyzer, QueryIntent
from grid_code.orchestrator.coordinator import Coordinator, SessionState
from grid_code.orchestrator.router import SubagentRouter

__all__ = [
    "Coordinator",
    "SessionState",
    "QueryAnalyzer",
    "QueryIntent",
    "SubagentRouter",
    "ResultAggregator",
]
