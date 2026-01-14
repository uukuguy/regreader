"""RegReader Subagents Framework

Pure configuration layer for multi-framework subagent support.

This module provides the shared configuration layer for all three framework
implementations (Claude Agent SDK, Pydantic AI, LangGraph).

Key Components:
    SubagentConfig: Configuration defining a subagent's tools and behavior.
    SubagentResult: Standardized result format for aggregation.
    SubagentType: Enumeration of subagent types (search, table, reference, discovery).
    RegSearchSubagent: Domain expert for regulation document retrieval.

Subagent Types:
    - RegSearchAgent (Domain): Regulation retrieval expert, integrates search/table/reference/discovery
    - SearchAgent: Document search and navigation (list_regulations, get_toc, smart_search)
    - TableAgent: Table search and extraction (search_tables, get_table_by_id)
    - ReferenceAgent: Cross-reference resolution (resolve_reference, lookup_annotation)
    - DiscoveryAgent: Semantic analysis (find_similar_content, compare_sections)

Example:
    >>> from regreader.subagents import SubagentType, SUBAGENT_CONFIGS
    >>> config = SUBAGENT_CONFIGS[SubagentType.REGSEARCH]
    >>> print(config.tools)
    ['list_regulations', 'get_toc', 'smart_search', ...]
"""

from regreader.orchestrator.result import SubagentResult
from regreader.subagents.config import (
    SUBAGENT_CONFIGS,
    SubagentConfig,
    SubagentType,
)
from regreader.subagents.regsearch import RegSearchSubagent

__all__ = [
    # Config
    "SubagentConfig",
    "SubagentType",
    "SUBAGENT_CONFIGS",
    # Result
    "SubagentResult",
    # Domain Subagents
    "RegSearchSubagent",
]
