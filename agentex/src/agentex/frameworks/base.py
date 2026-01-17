"""框架工厂

提供统一的 Agent 创建接口。
"""

from enum import Enum
from typing import Any

from ..agent import BaseAgent
from ..config import AgentConfig


class FrameworkType(str, Enum):
    """支持的框架类型"""
    CLAUDE = "claude"
    PYDANTIC = "pydantic"
    LANGGRAPH = "langgraph"


class FrameworkFactory:
    """框架工厂

    根据配置创建对应框架的 Agent 实例。
    """

    _instances: dict[FrameworkType, type] = {}

    @classmethod
    def register(cls, framework_type: FrameworkType):
        """注册框架实现类"""
        def decorator(agent_class: type):
            cls._instances[framework_type] = agent_class
            return agent_class
        return decorator

    @classmethod
    def create(
        cls,
        framework_type: FrameworkType,
        config: AgentConfig,
        **kwargs
    ) -> BaseAgent:
        """创建 Agent 实例

        Args:
            framework_type: 框架类型
            config: Agent 配置
            **kwargs: 额外参数

        Returns:
            Agent 实例

        Raises:
            ValueError: 不支持的框架类型
        """
        agent_class = cls._instances.get(framework_type)
        if agent_class is None:
            raise ValueError(
                f"不支持的框架类型: {framework_type}. "
                f"可用类型: {list(cls._instances.keys())}"
            )
        return agent_class(config, **kwargs)

    @classmethod
    def is_available(cls, framework_type: FrameworkType) -> bool:
        """检查框架是否可用"""
        return framework_type in cls._instances


def create_agent(
    framework: str,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    tools: list | None = None,
    system_prompt: str | None = None,
    **kwargs
) -> BaseAgent:
    """便捷工厂函数 - 创建 Agent

    Args:
        framework: 框架类型 ("claude", "pydantic", "langgraph")
        model: 模型名称（可选，从环境变量读取）
        api_key: API Key（可选，从环境变量读取）
        base_url: 基础 URL（可选，从环境变量读取）
        tools: 工具列表
        system_prompt: 系统提示词
        **kwargs: 额外参数

    Returns:
        Agent 实例
    """
    import os
    from ..config import AgentConfig
    from ..types import LLMConfig

    # 根据框架类型确定环境变量前缀
    framework_type = FrameworkType(framework)
    if framework_type == FrameworkType.CLAUDE:
        env_prefix = "ANTHROPIC"
    else:
        env_prefix = "OPENAI"

    # 从环境变量读取未提供的值
    if api_key is None:
        api_key = os.getenv(f"{env_prefix}_API_KEY")
    if base_url is None:
        base_url = os.getenv(f"{env_prefix}_BASE_URL")
    if model is None:
        model = os.getenv(f"{env_prefix}_MODEL_NAME")

    config = AgentConfig(
        name=f"{framework}-agent",
        llm=LLMConfig(
            model=model,
            api_key=api_key,
            base_url=base_url,
        ),
        tools=tools or [],
        system_prompt=system_prompt,
    )

    return FrameworkFactory.create(
        FrameworkType(framework),
        config,
        **kwargs
    )
