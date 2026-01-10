"""Pydantic AI Subagents 实现

基于 Pydantic AI v1.0+ 的 Subagents 协调器实现。
使用 Dependent Agents 模式，Subagent 作为 Orchestrator 的工具。
"""

from grid_code.agents.pydantic.orchestrator import PydanticOrchestrator
from grid_code.agents.pydantic.subagents import (
    BasePydanticSubagent,
    DiscoverySubagent,
    ReferenceSubagent,
    SearchSubagent,
    TableSubagent,
)

__all__ = [
    "PydanticOrchestrator",
    "BasePydanticSubagent",
    "SearchSubagent",
    "TableSubagent",
    "ReferenceSubagent",
    "DiscoverySubagent",
]
