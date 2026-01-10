"""GridCode Orchestrator Module

协调层，负责查询分析、Subagent 路由和结果聚合。

This module provides the coordination layer that analyzes user queries,
routes them to appropriate subagents, and aggregates the results.

Key Components:
    QueryAnalyzer: Analyzes user queries to determine intent and extract hints.
    QueryIntent: Result of query analysis (primary/secondary types, hints).
    SubagentRouter: Routes queries to appropriate subagents and executes them.
    ResultAggregator: Aggregates results from multiple subagents.

Workflow:
    1. QueryAnalyzer analyzes the user query
    2. SubagentRouter selects and executes appropriate subagents
    3. ResultAggregator combines the results into a unified response

Example:
    >>> from grid_code.orchestrator import QueryAnalyzer, SubagentRouter
    >>> analyzer = QueryAnalyzer()
    >>> intent = await analyzer.analyze("表6-2中注1的内容是什么？")
    >>> print(intent.primary_type)  # SubagentType.TABLE
    >>> print(intent.hints)  # {'table_hint': '表6-2', 'annotation_hint': '注1'}
"""

from grid_code.orchestrator.analyzer import QueryAnalyzer, QueryIntent
from grid_code.orchestrator.router import SubagentRouter
from grid_code.orchestrator.aggregator import ResultAggregator

__all__ = [
    "QueryAnalyzer",
    "QueryIntent",
    "SubagentRouter",
    "ResultAggregator",
]
