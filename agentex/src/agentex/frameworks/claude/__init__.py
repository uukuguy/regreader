"""Claude SDK Agent 实现

使用官方 Anthropic SDK 实现 Agent。
"""

from typing import AsyncGenerator

from agentex.agent import BaseAgent
from agentex.config import AgentConfig, LLMConfig
from agentex.shared import AgentMemory, StatusCallback, NullCallback
from agentex.shared.events import Event, EventType
from agentex.types import AgentResponse, AgentEvent, Context


class ClaudeAgent(BaseAgent):
    """基于 Anthropic SDK 的 Agent 实现

    使用官方 Anthropic Python SDK，支持流式响应和完整的 API 功能。
    """

    def __init__(
        self,
        config: AgentConfig,
        status_callback: StatusCallback | None = None,
    ):
        """初始化 Claude Agent

        Args:
            config: Agent 配置
            status_callback: 状态回调
        """
        self.config = config
        self.status_callback = status_callback or NullCallback()
        self._memory = AgentMemory() if config.memory_enabled else None

        # 初始化 Anthropic 客户端
        self._init_client()
        self._connected = False

    def _init_client(self):
        """初始化 Anthropic 客户端"""
        try:
            from anthropic import Anthropic
        except ImportError:
            raise ImportError(
                "Anthropic SDK not installed. "
                "Run: pip install anthropic"
            )

        llm = self.config.llm
        api_key = llm.api_key if llm else None
        base_url = llm.base_url if llm else None

        self._client = Anthropic(api_key=api_key, base_url=base_url)
        self._model = llm.model if llm else "claude-sonnet-4-20250514"

    @property
    def name(self) -> str:
        """获取 Agent 名称"""
        return self.config.name

    @property
    def model(self) -> str:
        """获取模型名称"""
        return self._model

    async def _ensure_connected(self):
        """确保已连接"""
        if not self._connected:
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
            # 构建消息历史（包含之前的对话）
            if self._memory:
                messages = self._memory.get_messages()
            else:
                messages = []

            # 添加当前用户消息
            messages.append({"role": "user", "content": message})

            # 添加系统提示词
            system_prompt = self.config.system_prompt

            # 调用 API
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=system_prompt,
                messages=messages,
            )

            # 提取文本内容（过滤掉 thinking blocks）
            text_blocks = [
                block.text for block in response.content
                if hasattr(block, 'text')
            ]
            result = "".join(text_blocks)

            # 添加用户消息到记忆（如果使用内存）
            if self._memory is not None:
                self._memory.add("user", message)

            # 添加助手回复到记忆
            if self._memory is not None:
                self._memory.add("assistant", result)

            # 发送思考结束事件
            await self.status_callback.on_event(
                AgentEvent(event_type="thinking_end", data={})
            )

            return AgentResponse(
                content=result,
                sources=[],
                metadata={"framework": "anthropic", "model": self._model}
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
            messages = [{"role": "user", "content": message}]
            system_prompt = self.config.system_prompt

            with self._client.messages.stream(
                model=self._model,
                max_tokens=4096,
                system=system_prompt,
                messages=messages,
            ) as stream:
                for chunk in stream:
                    if chunk.type == "content_block_delta":
                        if chunk.delta.type == "text_delta":
                            yield Event(
                                EventType.TEXT_DELTA,
                                data={"text": chunk.delta.text}
                            )
        finally:
            yield Event(EventType.THINKING_END)

    async def reset(self):
        """重置对话历史"""
        if self._memory:
            self._memory.clear()

    async def close(self):
        """释放资源"""
        self._connected = False


# 注册到工厂
from agentex.frameworks.base import FrameworkFactory, FrameworkType
FrameworkFactory.register(FrameworkType.CLAUDE)(ClaudeAgent)
