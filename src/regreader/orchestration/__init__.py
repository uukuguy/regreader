"""RegReader Orchestrator Module

协调层，负责查询分析、结果聚合和文件系统功能。

This module provides the coordination layer that analyzes user queries,
aggregates results, and manages file-based task tracking.

Key Components:
    Coordinator: File-based task tracking (plan.md, session_state.json, EventBus).
    QueryAnalyzer: Analyzes user queries to extract hints (chapter_scope, table_hint, etc.).
    ResultAggregator: Aggregates results from multiple subagents.

Workflow:
    1. QueryAnalyzer extracts hints from the query
    2. Coordinator logs query and hints to plan.md (optional)
    3. Framework (Claude SDK/Pydantic AI/LangGraph) autonomously selects subagents using LLM
    4. ResultAggregator combines the results into a unified response
    5. Coordinator logs results and updates session state (optional)

Note:
    SubagentRouter has been removed. Subagent selection is now handled by the
    frameworks' native LLM-based routing mechanisms.

Example:
    >>> from regreader.orchestrator import Coordinator
    >>> coordinator = Coordinator()
    >>> await coordinator.log_query("母线失压如何处理?", hints={}, reg_id="angui_2024")
    >>> # ... orchestrator executes query ...
    >>> await coordinator.write_result(content, sources, tool_calls)
"""

from regreader.orchestration.aggregator import ResultAggregator
from regreader.orchestration.analyzer import QueryAnalyzer
from regreader.orchestration.coordinator import Coordinator, SessionState

__all__ = [
    "Coordinator",
    "SessionState",
    "QueryAnalyzer",
    "ResultAggregator",
]
