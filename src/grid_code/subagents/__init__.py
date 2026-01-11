"""GridCode Subagents Framework

Unified subagent abstraction layer for multi-framework support.

This module provides the core abstractions shared across all three framework
implementations (Claude Agent SDK, Pydantic AI, LangGraph).

Key Components:
    BaseSubagent: Abstract base class for all subagent implementations.
    SubagentContext: Execution context passed from Orchestrator to Subagent.
    SubagentConfig: Configuration defining a subagent's tools and behavior.
    SubagentResult: Standardized result format for aggregation.
    SubagentType: Enumeration of subagent types (search, table, reference, discovery).
    SubagentRegistry: Registry for managing subagent instances.
    RegSearchSubagent: Domain expert for regulation document retrieval.

Subagent Types:
    - RegSearchAgent (Domain): Regulation retrieval expert, integrates search/table/reference/discovery
    - SearchAgent: Document search and navigation (list_regulations, get_toc, smart_search)
    - TableAgent: Table search and extraction (search_tables, get_table_by_id)
    - ReferenceAgent: Cross-reference resolution (resolve_reference, lookup_annotation)
    - DiscoveryAgent: Semantic analysis (find_similar_content, compare_sections)

Example:
    >>> from grid_code.subagents import SubagentType, SUBAGENT_CONFIGS
    >>> config = SUBAGENT_CONFIGS[SubagentType.REGSEARCH]
    >>> print(config.tools)
    ['list_regulations', 'get_toc', 'smart_search', ...]
"""

from grid_code.subagents.base import BaseSubagent, SubagentContext
from grid_code.subagents.config import (
    SUBAGENT_CONFIGS,
    SubagentConfig,
    SubagentType,
)
from grid_code.subagents.registry import SubagentRegistry
from grid_code.subagents.regsearch import RegSearchSubagent
from grid_code.subagents.result import SubagentResult

__all__ = [
    # Base classes
    "BaseSubagent",
    "SubagentContext",
    # Config
    "SubagentConfig",
    "SubagentType",
    "SUBAGENT_CONFIGS",
    # Result
    "SubagentResult",
    # Registry
    "SubagentRegistry",
    # Domain Subagents
    "RegSearchSubagent",
]
