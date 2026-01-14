"""Agent 抽象基类

定义 RegReader Agent 的统一接口。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AgentResponse:
    """Agent 响应"""

    content: str  # 回答内容
    sources: list[str]  # 来源引用列表
    tool_calls: list[dict]  # 工具调用记录


class BaseRegReaderAgent(ABC):
    """RegReader Agent 抽象基类

    所有 Agent 实现必须继承此类并实现 chat 方法。
    """

    def __init__(self, reg_id: str | None = None):
        """
        初始化 Agent

        Args:
            reg_id: 默认规程标识（可选，如果指定则限定在该规程内检索）
        """
        self.reg_id = reg_id

    @abstractmethod
    async def chat(self, message: str) -> AgentResponse:
        """
        与 Agent 对话

        Args:
            message: 用户消息

        Returns:
            AgentResponse 包含回答内容和来源引用
        """
        pass

    @abstractmethod
    async def reset(self):
        """重置对话历史"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent 名称"""
        pass

    @property
    @abstractmethod
    def model(self) -> str:
        """使用的模型名称"""
        pass
