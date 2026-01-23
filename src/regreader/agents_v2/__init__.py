"""RegReader Agents V2 - 基于 AgentEx 的实现

使用 agentex 框架重新实现 RegReader Agent，保留所有领域特定功能。

模块结构:
- base.py: RegReaderAgent 基础包装类
- config.py: RegReaderConfig 配置类
- memory.py: RegReaderMemory 扩展记忆系统
- events.py: EventAdapter 事件适配器
- direct/: 直接 Agent 实现 (Claude, Pydantic, LangGraph)
- orchestrated/: Orchestrator 实现
"""

from __future__ import annotations

from .base import AgentResponse, RegReaderAgent
from .config import (
    ClaudeAgentConfig,
    LangGraphAgentConfig,
    OrchestratorConfig,
    PydanticAgentConfig,
    RegReaderConfig,
)
from .events import EventAdapter
from .memory import ContentChunk, RegReaderMemory

# 延迟导入 Agent 类，避免循环依赖
__all__ = [
    # 基础类
    "RegReaderAgent",
    "AgentResponse",
    # 配置类
    "RegReaderConfig",
    "ClaudeAgentConfig",
    "PydanticAgentConfig",
    "LangGraphAgentConfig",
    "OrchestratorConfig",
    # 记忆系统
    "RegReaderMemory",
    "ContentChunk",
    # 事件适配器
    "EventAdapter",
    # Direct Agents
    "ClaudeAgent",
    "PydanticAIAgent",
    "LangGraphAgent",
    # Orchestrators
    "BaseOrchestrator",
    "ClaudeOrchestrator",
    "PydanticOrchestrator",
    "LangGraphOrchestrator",
]


def __getattr__(name: str):
    """延迟导入 Agent 类"""
    # Direct Agents
    if name == "ClaudeAgent":
        from .direct import ClaudeAgent
        return ClaudeAgent
    elif name == "PydanticAIAgent":
        from .direct import PydanticAIAgent
        return PydanticAIAgent
    elif name == "LangGraphAgent":
        from .direct import LangGraphAgent
        return LangGraphAgent
    # Orchestrators
    elif name == "BaseOrchestrator":
        from .orchestrated import BaseOrchestrator
        return BaseOrchestrator
    elif name == "ClaudeOrchestrator":
        from .orchestrated import ClaudeOrchestrator
        return ClaudeOrchestrator
    elif name == "PydanticOrchestrator":
        from .orchestrated import PydanticOrchestrator
        return PydanticOrchestrator
    elif name == "LangGraphOrchestrator":
        from .orchestrated import LangGraphOrchestrator
        return LangGraphOrchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
