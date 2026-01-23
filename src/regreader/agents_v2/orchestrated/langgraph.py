"""LangGraph Orchestrator 实现

基于 agentex 框架的 LangGraph Orchestrator。

注意：此模块直接复用旧的 LangGraphOrchestrator 实现，
因为 OrchestratorAgent 包含完整的规划-执行-聚合逻辑。
"""

from __future__ import annotations

# 直接从旧实现导入，保持完整功能
from ...agents.orchestrated.langgraph import LangGraphOrchestrator

__all__ = ["LangGraphOrchestrator"]
