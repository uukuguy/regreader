"""Claude Agent SDK Subagents 实现

基于 Claude Agent SDK 的 Subagents 协调器实现。
使用 Handoff Pattern，每个 Subagent 是独立的 ClaudeSDKClient 实例。
"""

from regreader.agents.claude.orchestrator import ClaudeOrchestrator
from regreader.agents.claude.subagents import (
    BaseClaudeSubagent,
    DiscoverySubagent,
    ReferenceSubagent,
    SearchSubagent,
    TableSubagent,
)

__all__ = [
    "ClaudeOrchestrator",
    "BaseClaudeSubagent",
    "SearchSubagent",
    "TableSubagent",
    "ReferenceSubagent",
    "DiscoverySubagent",
]
