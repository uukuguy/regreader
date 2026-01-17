"""框架配置

定义 Agent 配置。
"""

import os
from dataclasses import dataclass, field
from typing import Any, Callable

from ..types import LLMConfig, ToolConfig, Context


@dataclass
class AgentConfig:
    """Agent 配置

    完全通用化，不包含任何领域特定配置。
    """

    name: str = "agent"
    """Agent 名称"""

    llm: LLMConfig | None = None
    """LLM 配置"""

    system_prompt: str | None = None
    """系统提示词"""

    system_prompt_builder: Callable[[], str] | None = None
    """动态系统提示词构建器"""

    tools: list = field(default_factory=list)
    """工具列表"""

    tool_registry = None  # 延迟引用
    """工具注册表"""

    memory_enabled: bool = True
    """是否启用记忆"""

    max_history: int = 50
    """最大历史消息数"""

    max_iterations: int = 10
    """最大迭代次数"""

    timeout_seconds: float = 60.0
    """超时时间"""

    event_callback: Callable | None = None
    """事件回调"""

    @property
    def model(self) -> str | None:
        """获取模型名称"""
        return self.llm.model if self.llm else None


@dataclass
class ClaudeConfig(AgentConfig):
    """Claude 专用配置"""

    api_key: str | None = field(default_factory=lambda: os.getenv("ANTHROPIC_AUTH_TOKEN"))
    """API Key"""

    base_url: str | None = field(default_factory=lambda: os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com"))
    """基础 URL"""

    model: str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL_NAME", "claude-sonnet-4-20250514"))
    """模型名称"""

    use_preset: bool = True
    """是否使用 Anthropic preset"""

    mcp_servers: dict | None = None
    """MCP 服务器配置"""

    def __post_init__(self):
        self.llm = LLMConfig(
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
        )


@dataclass
class PydanticConfig(AgentConfig):
    """Pydantic AI 专用配置"""

    api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    """API Key"""

    base_url: str | None = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    """基础 URL"""

    model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL_NAME", "gpt-4"))
    """模型名称"""

    def __post_init__(self):
        self.llm = LLMConfig(
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
        )


@dataclass
class LangGraphConfig(AgentConfig):
    """LangGraph 专用配置"""

    api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    """API Key"""

    base_url: str | None = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    """基础 URL"""

    model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL_NAME", "gpt-4"))
    """模型名称"""

    state_schema: type | None = None
    """状态 schema"""

    checkpointer: Any = None
    """检查点存储器"""

    def __post_init__(self):
        self.llm = LLMConfig(
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
        )
