"""Subagent 注册表

管理 Subagent 配置和框架特定工厂的注册。
"""

from typing import TYPE_CHECKING

from regreader.subagents.config import (
    SUBAGENT_CONFIGS,
    SubagentConfig,
    SubagentType,
)
from regreader.subagents.prompts import inject_prompt_to_config

if TYPE_CHECKING:
    from regreader.subagents.base import BaseSubagent


class SubagentRegistry:
    """Subagent 注册表

    管理 Subagent 配置和框架特定实现的注册。
    提供工厂方法创建框架特定的 Subagent 实例。

    Usage:
        # 初始化（应用启动时）
        SubagentRegistry.initialize()

        # 注册框架实现
        SubagentRegistry.register_factory("langgraph", SubagentType.SEARCH, LangGraphSearchSubagent)

        # 创建实例
        subagent = SubagentRegistry.create_subagent("langgraph", SubagentType.SEARCH)
    """

    _initialized: bool = False
    _configs: dict[SubagentType, SubagentConfig] = {}
    _factories: dict[str, dict[SubagentType, type["BaseSubagent"]]] = {}

    @classmethod
    def initialize(cls) -> None:
        """初始化注册表

        加载默认配置并注入提示词。
        应在应用启动时调用一次。
        """
        if cls._initialized:
            return

        # 注入提示词到配置
        inject_prompt_to_config()

        # 加载配置
        cls._configs = SUBAGENT_CONFIGS.copy()
        cls._initialized = True

    @classmethod
    def register_config(
        cls,
        agent_type: SubagentType,
        config: SubagentConfig,
    ) -> None:
        """注册或更新 Subagent 配置

        Args:
            agent_type: Subagent 类型
            config: 配置对象
        """
        cls._configs[agent_type] = config

    @classmethod
    def register_factory(
        cls,
        framework: str,
        agent_type: SubagentType,
        factory: type["BaseSubagent"],
    ) -> None:
        """注册框架特定的 Subagent 工厂

        Args:
            framework: 框架名（"claude", "pydantic", "langgraph"）
            agent_type: Subagent 类型
            factory: Subagent 类（继承自 BaseSubagent）
        """
        if framework not in cls._factories:
            cls._factories[framework] = {}
        cls._factories[framework][agent_type] = factory

    @classmethod
    def get_config(cls, agent_type: SubagentType) -> SubagentConfig:
        """获取 Subagent 配置

        Args:
            agent_type: Subagent 类型

        Returns:
            配置对象

        Raises:
            KeyError: 类型未注册
        """
        if not cls._initialized:
            cls.initialize()
        return cls._configs[agent_type]

    @classmethod
    def get_enabled_configs(cls) -> list[SubagentConfig]:
        """获取所有启用的配置

        Returns:
            启用的配置列表，按优先级排序
        """
        if not cls._initialized:
            cls.initialize()
        configs = [c for c in cls._configs.values() if c.enabled]
        return sorted(configs, key=lambda c: c.priority)

    @classmethod
    def get_enabled_types(cls) -> list[SubagentType]:
        """获取所有启用的 Subagent 类型

        Returns:
            启用的类型列表
        """
        return [c.agent_type for c in cls.get_enabled_configs()]

    @classmethod
    def create_subagent(
        cls,
        framework: str,
        agent_type: SubagentType,
    ) -> "BaseSubagent":
        """创建 Subagent 实例

        Args:
            framework: 框架名
            agent_type: Subagent 类型

        Returns:
            Subagent 实例

        Raises:
            ValueError: 框架或类型未注册
        """
        if not cls._initialized:
            cls.initialize()

        if framework not in cls._factories:
            raise ValueError(f"Unknown framework: {framework}")
        if agent_type not in cls._factories[framework]:
            raise ValueError(
                f"No factory registered for {agent_type.value} in {framework}"
            )

        config = cls.get_config(agent_type)
        factory = cls._factories[framework][agent_type]
        return factory(config)

    @classmethod
    def create_all_subagents(cls, framework: str) -> dict[SubagentType, "BaseSubagent"]:
        """创建框架的所有启用 Subagent

        Args:
            framework: 框架名

        Returns:
            类型到实例的映射
        """
        subagents = {}
        for agent_type in cls.get_enabled_types():
            try:
                subagents[agent_type] = cls.create_subagent(framework, agent_type)
            except ValueError:
                # 该类型未注册工厂，跳过
                pass
        return subagents

    @classmethod
    def has_factory(cls, framework: str, agent_type: SubagentType) -> bool:
        """检查是否注册了工厂

        Args:
            framework: 框架名
            agent_type: Subagent 类型

        Returns:
            是否已注册
        """
        return (
            framework in cls._factories
            and agent_type in cls._factories[framework]
        )

    @classmethod
    def get_registered_frameworks(cls) -> list[str]:
        """获取已注册工厂的框架列表

        Returns:
            框架名列表
        """
        return list(cls._factories.keys())

    @classmethod
    def reset(cls) -> None:
        """重置注册表（仅用于测试）"""
        cls._initialized = False
        cls._configs.clear()
        cls._factories.clear()
