"""RegReader Agent 基础包装类

在 agentex.BaseAgent 基础上添加 RegReader 特定功能。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

from ..agentex.agent import BaseAgent
from ..agentex.types import AgentResponse as AgentexResponse
from ..agentex.types import Context
from ..agents.session import SessionManager, SessionState
from ..agents.shared.callbacks import NullCallback, StatusCallback
from .config import RegReaderConfig
from .events import EventAdapter
from .memory import RegReaderMemory


@dataclass
class AgentResponse:
    """RegReader Agent 响应

    与现有 agents.base.AgentResponse 保持兼容。
    """

    content: str
    """回答内容"""

    sources: list[str] = field(default_factory=list)
    """来源引用列表"""

    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    """工具调用记录"""

    metadata: dict[str, Any] = field(default_factory=dict)
    """元数据（扩展字段）"""

    @classmethod
    def from_agentex(cls, response: AgentexResponse) -> "AgentResponse":
        """从 agentex AgentResponse 转换

        Args:
            response: agentex 响应

        Returns:
            RegReader 响应
        """
        return cls(
            content=response.content,
            sources=response.sources,
            tool_calls=response.tool_calls,
            metadata=response.metadata,
        )


class RegReaderAgent(ABC):
    """RegReader Agent 抽象基类

    在 agentex.BaseAgent 基础上添加:
    - reg_id 规程限定
    - 会话管理 (SessionManager)
    - 记忆系统 (RegReaderMemory)
    - 来源提取
    - 事件适配

    子类需要实现 _create_agent() 方法来创建底层 agentex Agent。
    """

    def __init__(
        self,
        config: RegReaderConfig | None = None,
        reg_id: str | None = None,
        status_callback: StatusCallback | None = None,
    ):
        """初始化 RegReader Agent

        Args:
            config: RegReader 配置（可选）
            reg_id: 默认规程标识（可选，会覆盖 config 中的值）
            status_callback: 状态回调（可选）
        """
        self._config = config or RegReaderConfig()

        # reg_id 优先使用参数，其次使用 config
        if reg_id is not None:
            self._config.reg_id = reg_id

        # 会话管理器
        self._session_manager = SessionManager()

        # 记忆系统
        self._memory: RegReaderMemory | None = None
        if self._config.enable_memory:
            self._memory = RegReaderMemory()

        # 状态回调
        self._callback = status_callback or self._config.status_callback or NullCallback()

        # 底层 agentex Agent（延迟初始化）
        self._agent: BaseAgent | None = None

        # 工具调用追踪
        self._tool_start_times: dict[str, float] = {}

    @property
    def reg_id(self) -> str | None:
        """默认规程标识"""
        return self._config.reg_id

    @reg_id.setter
    def reg_id(self, value: str | None) -> None:
        """设置默认规程标识"""
        self._config.reg_id = value

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

    @property
    def memory(self) -> RegReaderMemory | None:
        """记忆系统"""
        return self._memory

    @property
    def session_manager(self) -> SessionManager:
        """会话管理器"""
        return self._session_manager

    @abstractmethod
    async def _create_agent(self) -> BaseAgent:
        """创建底层 agentex Agent

        子类必须实现此方法，返回配置好的 agentex Agent 实例。

        Returns:
            agentex BaseAgent 实例
        """
        ...

    async def _ensure_agent(self) -> BaseAgent:
        """确保 Agent 已初始化

        Returns:
            agentex BaseAgent 实例
        """
        if self._agent is None:
            self._agent = await self._create_agent()
        return self._agent

    async def chat(
        self,
        message: str,
        session_id: str | None = None,
    ) -> AgentResponse:
        """与 Agent 对话

        Args:
            message: 用户消息
            session_id: 会话 ID（可选，用于多会话隔离）

        Returns:
            AgentResponse 包含回答内容和来源引用
        """
        import time

        from .events import EventAdapter

        # 获取或创建会话
        session = self._session_manager.get_or_create(session_id)
        session.reset_per_query()

        # 重置工具追踪状态
        self._tool_start_times = {}

        # 记录开始时间
        start_time = time.time()

        # 发送思考开始事件
        await self._callback.on_event(EventAdapter.create_thinking_event(start=True))

        try:
            # 确保 Agent 已初始化
            agent = await self._ensure_agent()

            # 构建上下文
            context = self._build_context(session)

            # 调用底层 Agent
            agentex_response = await agent.chat(message, context=context)

            # 提取来源
            self._extract_sources_from_response(agentex_response, session)

            # 更新记忆
            if self._memory:
                self._update_memory_from_response(agentex_response)

            # 转换响应
            response = AgentResponse.from_agentex(agentex_response)

            # 合并会话中收集的来源
            response.sources = list(set(response.sources + session.sources))
            response.tool_calls = session.tool_calls or response.tool_calls

        except Exception as e:
            # 发送思考结束事件
            await self._callback.on_event(EventAdapter.create_thinking_event(start=False))
            raise

        # 发送思考结束事件
        await self._callback.on_event(EventAdapter.create_thinking_event(start=False))

        # 计算总耗时
        duration_ms = (time.time() - start_time) * 1000

        # 发送响应完成事件
        await self._callback.on_event(
            EventAdapter.create_response_complete_event(
                content=response.content,
                sources=response.sources,
            )
        )

        return response

    async def stream(
        self,
        message: str,
        session_id: str | None = None,
    ) -> AsyncGenerator[Any, None]:
        """流式响应

        Args:
            message: 用户消息
            session_id: 会话 ID

        Yields:
            AgentEvent 事件
        """
        from .events import EventAdapter

        # 获取或创建会话
        session = self._session_manager.get_or_create(session_id)
        session.reset_per_query()

        # 确保 Agent 已初始化
        agent = await self._ensure_agent()

        # 构建上下文
        context = self._build_context(session)

        # 流式调用底层 Agent
        async for event in agent.stream(message, context=context):
            # 转换事件
            regreader_event = EventAdapter.to_regreader_event(event)

            # 发送到回调
            await self._callback.on_event(regreader_event)

            yield regreader_event

    def _build_context(self, session: SessionState) -> Context:
        """构建对话上下文

        Args:
            session: 会话状态

        Returns:
            上下文字典
        """
        context: Context = {}

        # 添加 reg_id
        if self.reg_id:
            context["reg_id"] = self.reg_id

        # 添加记忆上下文
        if self._memory:
            memory_context = self._memory.get_memory_context()
            if memory_context:
                context["memory"] = memory_context

            # TOC 缓存提示
            toc_hint = self._memory.get_toc_cache_hint()
            if toc_hint:
                context["toc_hint"] = toc_hint

        # 添加会话信息
        context["session_id"] = session.session_id

        return context

    def _extract_sources_from_response(
        self, response: AgentexResponse, session: SessionState
    ) -> None:
        """从响应中提取来源

        Args:
            response: agentex 响应
            session: 会话状态
        """
        # 从 sources 字段提取
        for source in response.sources:
            session.add_source(source)

        # 从 tool_calls 中提取
        for tool_call in response.tool_calls:
            output = tool_call.get("output")
            if output:
                self._extract_sources(output, session)

            # 记录到会话
            session.add_tool_call(
                name=tool_call.get("name", "unknown"),
                input_data=tool_call.get("input", {}),
                output=output,
            )

    def _extract_sources(self, result: Any, session: SessionState) -> None:
        """从工具结果中提取来源信息

        支持多种结果格式：
        - dict: 检查 source 字段
        - list: 递归处理每个元素
        - str: 尝试解析为 JSON

        Args:
            result: 工具结果
            session: 会话状态
        """
        if result is None:
            return

        if isinstance(result, dict):
            # 直接检查 source 字段
            if "source" in result and result["source"]:
                session.add_source(result["source"])

            # 递归处理嵌套
            for key, value in result.items():
                if key != "source":
                    self._extract_sources(value, session)

        elif isinstance(result, list):
            for item in result:
                self._extract_sources(item, session)

        elif isinstance(result, str):
            # 尝试解析 JSON
            try:
                import json

                parsed = json.loads(result)
                self._extract_sources(parsed, session)
            except (json.JSONDecodeError, TypeError):
                pass

    def _update_memory_from_response(self, response: AgentexResponse) -> None:
        """从响应更新记忆系统

        Args:
            response: agentex 响应
        """
        if not self._memory:
            return

        import json

        for tool_call in response.tool_calls:
            tool_name = tool_call.get("name", "")
            result = tool_call.get("output")

            if not result:
                continue

            # 解析 JSON 字符串
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except (json.JSONDecodeError, TypeError):
                    continue

            if not isinstance(result, dict):
                continue

            # 提取真实工具名（去除 mcp__gridcode__ 前缀）
            simple_name = tool_name
            if "__" in tool_name:
                parts = tool_name.split("__")
                simple_name = parts[-1] if len(parts) > 1 else tool_name

            # 根据工具类型更新记忆
            if simple_name == "get_toc":
                reg_id = result.get("reg_id") or self.reg_id
                if reg_id:
                    self._memory.cache_toc(reg_id, result)

            elif simple_name == "smart_search":
                results = result.get("results", [])
                if results:
                    self._memory.add_search_results(results, self.reg_id)

    async def reset(self, session_id: str | None = None) -> None:
        """重置对话历史

        Args:
            session_id: 要重置的会话 ID，如果为 None 则重置默认会话
        """
        self._session_manager.reset(session_id)

        if self._memory:
            self._memory.clear_query_context()

        if self._agent:
            await self._agent.reset()

    async def reset_all(self) -> None:
        """重置所有会话"""
        self._session_manager.reset_all()

        if self._memory:
            self._memory.clear()

        if self._agent:
            await self._agent.reset()

    async def close(self) -> None:
        """释放资源"""
        if self._agent:
            await self._agent.close()
            self._agent = None

    def get_sessions(self) -> list[str]:
        """获取所有活跃会话 ID"""
        return self._session_manager.get_all_sessions()

    def get_session_info(self, session_id: str | None = None) -> dict | None:
        """获取会话信息"""
        return self._session_manager.get_session_info(session_id)

    async def __aenter__(self) -> "RegReaderAgent":
        """异步上下文管理器入口"""
        await self._ensure_agent()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        await self.close()
