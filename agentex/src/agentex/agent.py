"""Agent 抽象基类

定义统一的 Agent 接口规范。
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator

from .types import AgentResponse, AgentEvent, Context


class BaseAgent(ABC):
    """所有 Agent 的抽象基类

    定义统一的接口规范，各框架实现需继承此类。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent 名称"""
        ...

    @property
    @abstractmethod
    def model(self) -> str:
        """使用的模型名称"""
        ...

    @abstractmethod
    async def chat(
        self,
        message: str,
        context: Context | None = None
    ) -> AgentResponse:
        """发送消息并获取响应

        Args:
            message: 用户消息
            context: 可选的对话上下文

        Returns:
            AgentResponse: 包含回答和元数据
        """
        ...

    @abstractmethod
    async def stream(
        self,
        message: str,
        context: Context | None = None
    ) -> AsyncGenerator[AgentEvent, None]:
        """流式响应

        Args:
            message: 用户消息
            context: 可选的对话上下文

        Yields:
            AgentEvent: 实时事件（思考、工具调用、文本增量等）
        """
        ...

    @abstractmethod
    async def reset(self):
        """重置对话历史和状态"""
        ...

    @abstractmethod
    async def close(self):
        """释放资源（关闭连接等）"""
        ...


class AgentState:
    """Agent 状态管理

    管理对话历史和运行时状态。
    """

    def __init__(self, max_history: int = 50):
        self.max_history = max_history
        self._history: list[dict[str, Any]] = []
        self._metadata: dict[str, Any] = {}

    def add_message(self, role: str, content: str, metadata: dict[str, Any] | None = None):
        """添加消息到历史"""
        message = {
            "role": role,
            "content": content,
            "metadata": metadata or {}
        }
        self._history.append(message)

        # 裁剪超出的历史
        if len(self._history) > self.max_history:
            self._history = self._history[-self.max_history:]

    def get_history(self) -> list[dict[str, Any]]:
        """获取对话历史"""
        return list(self._history)

    def clear(self):
        """清空状态"""
        self._history.clear()
        self._metadata.clear()

    def get_context(self) -> dict[str, Any]:
        """获取当前上下文"""
        return {
            "history": self._history,
            "metadata": self._metadata,
        }

    def __len__(self):
        return len(self._history)
