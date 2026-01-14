"""Pydantic AI Subagents 实现

基于 Pydantic AI v1.0+ 的 Subagents 协调器实现。
使用原生的 Agent 委托模式:
- Orchestrator 通过 @tool 装饰器注册委托工具
- 使用 deps/usage 传递实现依赖注入和使用量追踪
"""

from regreader.agents.pydantic.orchestrator import (
    OrchestratorDependencies,
    PydanticOrchestrator,
    create_orchestrator_agent,
)
from regreader.agents.pydantic.subagents import (
    # 新的构建器 API
    SubagentBuilder,
    SubagentDependencies,
    SubagentOutput,
    create_subagent_builder,
    # Legacy 类（向后兼容）
    BasePydanticSubagent,
    DiscoverySubagent,
    ReferenceSubagent,
    SearchSubagent,
    TableSubagent,
)

__all__ = [
    # Orchestrator
    "PydanticOrchestrator",
    "OrchestratorDependencies",
    "create_orchestrator_agent",
    # Subagent Builder API
    "SubagentBuilder",
    "SubagentDependencies",
    "SubagentOutput",
    "create_subagent_builder",
    # Legacy (backward compatibility)
    "BasePydanticSubagent",
    "SearchSubagent",
    "TableSubagent",
    "ReferenceSubagent",
    "DiscoverySubagent",
]
