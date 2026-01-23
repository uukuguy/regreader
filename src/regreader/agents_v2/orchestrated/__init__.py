"""Orchestrated Agents - 基于 Orchestrator 模式的 Agent 实现

提供三种框架的 Orchestrator 实现：
- ClaudeOrchestrator: 基于 Claude Agent SDK
- PydanticOrchestrator: 基于 Pydantic AI
- LangGraphOrchestrator: 基于 LangGraph
"""

from __future__ import annotations

__all__ = [
    "BaseOrchestrator",
    "ClaudeOrchestrator",
    "PydanticOrchestrator",
    "LangGraphOrchestrator",
]


def __getattr__(name: str):
    """延迟导入 Orchestrator 类"""
    if name == "BaseOrchestrator":
        from .base import BaseOrchestrator
        return BaseOrchestrator
    elif name == "ClaudeOrchestrator":
        from .claude import ClaudeOrchestrator
        return ClaudeOrchestrator
    elif name == "PydanticOrchestrator":
        from .pydantic import PydanticOrchestrator
        return PydanticOrchestrator
    elif name == "LangGraphOrchestrator":
        from .langgraph import LangGraphOrchestrator
        return LangGraphOrchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
