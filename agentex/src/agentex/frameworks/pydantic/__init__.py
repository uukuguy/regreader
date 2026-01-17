"""Pydantic AI Agent 实现

使用 Pydantic AI 框架实现 Agent。
"""

from typing import AsyncGenerator

from agentex.agent import BaseAgent
from agentex.config import AgentConfig
from agentex.shared import AgentMemory, StatusCallback, NullCallback
from agentex.shared.events import Event, EventType
from agentex.types import AgentResponse, AgentEvent, Context


class PydanticAgent(BaseAgent):
    """基于 Pydantic AI 的 Agent 实现

    使用 Pydantic AI v1.0+ 框架，支持依赖注入和工具集成。
    """

    def __init__(
        self,
        config: AgentConfig,
        status_callback: StatusCallback | None = None,
    ):
        """初始化 Pydantic Agent

        Args:
            config: Agent 配置
            status_callback: 状态回调
        """
        self.config = config
        self.status_callback = status_callback or NullCallback()
        self._memory = AgentMemory() if config.memory_enabled else None

        # 初始化 Pydantic AI（延迟导入）
        self._init_agent()
        self._connected = False

    def _init_agent(self):
        """初始化 Pydantic AI Agent"""
        try:
            from pydantic_ai import Agent
            from pydantic_ai.providers.openai import OpenAIProvider
            from pydantic_ai.models.openai import OpenAIChatModel
        except ImportError:
            raise ImportError(
                "Pydantic AI not installed. "
                "Run: pip install 'pydantic-ai>=1.0.0'"
            )

        llm = self.config.llm
        model_name = llm.model if llm else "gpt-4"

        # 根据 base_url 判断后端
        base_url = llm.base_url if llm else None
        if base_url and "ollama" in base_url.lower():
            # Ollama 特殊处理
            if not base_url.endswith("/v1"):
                base_url = base_url.rstrip("/") + "/v1"
            provider = OpenAIProvider(base_url=base_url, api_key="ollama")
            model = OpenAIChatModel(model_name=model_name, provider=provider)
        else:
            model = f"openai:{model_name}"

        # 创建 Agent
        self._agent = Agent(model)
        self._PydanticAgent = Agent

    @property
    def name(self) -> str:
        """获取 Agent 名称"""
        return self.config.name

    @property
    def model(self) -> str:
        """获取模型名称"""
        return self.config.llm.model if self.config.llm else "unknown"

    async def _ensure_connected(self):
        """确保已连接"""
        if not self._connected:
            await self._agent.__aenter__()
            self._connected = True

    async def chat(
        self,
        message: str,
        context: Context | None = None
    ) -> AgentResponse:
        """发送消息并获取响应"""
        await self._ensure_connected()

        # 发送思考开始事件
        await self.status_callback.on_event(
            AgentEvent(event_type="thinking_start", data={"message": message})
        )

        try:
            # 获取历史消息用于上下文
            message_history = None
            if self._memory:
                message_history = self._memory.get_messages()

            # 调用 Agent（传递历史消息）
            result = await self._agent.run(message, message_history=message_history)

            # 添加用户消息到记忆（如果使用内存）
            if self._memory is not None:
                self._memory.add("user", message)

            # 添加助手回复到记忆
            if self._memory is not None:
                self._memory.add("assistant", result.output)

            # 发送思考结束事件
            await self.status_callback.on_event(
                AgentEvent(event_type="thinking_end", data={})
            )

            return AgentResponse(
                content=result.output,
                sources=[],
                metadata={"framework": "pydantic-ai"}
            )

        except Exception as e:
            await self.status_callback.on_event(
                AgentEvent(event_type="error", data={"error": str(e)})
            )
            raise

    async def stream(
        self,
        message: str,
        context: Context | None = None
    ) -> AsyncGenerator[AgentEvent, None]:
        """流式响应"""
        await self._ensure_connected()

        yield Event(EventType.THINKING_START)

        try:
            async with self._agent.run_stream(message) as result:
                async for chunk in result.stream_text():
                    yield Event(
                        EventType.TEXT_DELTA,
                        data={"text": chunk}
                    )
        finally:
            yield Event(EventType.THINKING_END)

    async def reset(self):
        """重置对话历史"""
        if self._memory:
            self._memory.clear()

    async def close(self):
        """释放资源"""
        if self._connected:
            await self._agent.__aexit__(None, None, None)
            self._connected = False


# 注册到工厂
from agentex.frameworks.base import FrameworkFactory, FrameworkType
FrameworkFactory.register(FrameworkType.PYDANTIC)(PydanticAgent)
