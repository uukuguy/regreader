"""RegReader Agent 配置

定义 RegReader 特定的 Agent 配置类。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from ..agents.shared.mcp_connection import MCPConnectionConfig
from ..agents.shared.callbacks import StatusCallback


@dataclass
class RegReaderConfig:
    """RegReader 特定的 Agent 配置

    封装领域特定配置，与 agentex 通用配置分离。
    """

    # 领域特定配置
    reg_id: str | None = None
    """默认规程标识（可选，如果指定则限定在该规程内检索）"""

    enable_memory: bool = True
    """是否启用记忆系统"""

    enable_toc_cache: bool = True
    """是否启用 TOC 缓存"""

    prompt_mode: Literal["full", "optimized", "simple"] = "optimized"
    """提示词模式: full=完整版, optimized=优化版, simple=简化版"""

    # MCP 配置
    mcp_config: MCPConnectionConfig | None = None
    """MCP 连接配置"""

    # 回调配置
    status_callback: StatusCallback | None = None
    """状态回调"""

    # Agent 配置
    model: str | None = None
    """模型名称（可选，默认从环境变量读取）"""

    system_prompt: str | None = None
    """自定义系统提示词（可选，默认使用领域提示词）"""

    max_iterations: int = 10
    """最大迭代次数"""

    timeout_seconds: float = 120.0
    """超时时间（秒）"""

    # 扩展配置
    extra: dict[str, Any] = field(default_factory=dict)
    """额外配置参数"""


@dataclass
class ClaudeAgentConfig(RegReaderConfig):
    """Claude Agent 特定配置"""

    use_preset: bool = True
    """是否使用 Anthropic preset (claude_code)"""

    enable_hooks: bool = True
    """是否启用审计钩子"""


@dataclass
class PydanticAgentConfig(RegReaderConfig):
    """Pydantic AI Agent 特定配置"""

    pass


@dataclass
class LangGraphAgentConfig(RegReaderConfig):
    """LangGraph Agent 特定配置"""

    enable_checkpointer: bool = True
    """是否启用检查点"""


@dataclass
class OrchestratorConfig(RegReaderConfig):
    """Orchestrator 特定配置"""

    use_coordinator: bool = False
    """是否使用 Coordinator 进行文件日志"""

    parallel_mode: bool = False
    """是否启用并行执行子任务"""

    max_subtasks: int = 10
    """最大子任务数"""
