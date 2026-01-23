"""Pydantic AI Agent 实现

基于 agentex 框架的 Pydantic AI Agent。
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterable
from dataclasses import dataclass
from typing import Any, AsyncGenerator

from loguru import logger

from ...agentex.agent import BaseAgent
from ...agentex.types import AgentResponse as AgentexResponse, Context
from ...agents.prompts import (
    get_full_prompt,
    get_optimized_prompt_with_domain,
    get_simple_prompt,
)
from ...agents.shared.callbacks import StatusCallback
from ...agents.shared.mcp_connection import MCPConnectionConfig, get_mcp_manager
from ...core.config import get_settings
from ...storage import PageStore
from ..base import AgentResponse, RegReaderAgent
from ..config import PydanticAgentConfig, RegReaderConfig
from ..events import EventAdapter

# Pydantic AI imports
try:
    from pydantic_ai import Agent, RunContext
    from pydantic_ai.mcp import MCPServerStdio
    from pydantic_ai.messages import (
        AgentStreamEvent,
        FinalResultEvent,
        FunctionToolCallEvent,
        FunctionToolResultEvent,
        ModelMessage,
        PartDeltaEvent,
        PartStartEvent,
        TextPartDelta,
        ThinkingPartDelta,
    )
    import httpx
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
    from pydantic_ai.profiles.openai import OpenAIModelProfile

    HAS_PYDANTIC_AI = True
except ImportError:
    HAS_PYDANTIC_AI = False
    Agent = None  # type: ignore
    RunContext = None  # type: ignore
    MCPServerStdio = None  # type: ignore
    ModelMessage = None  # type: ignore
    AgentStreamEvent = None  # type: ignore
    FinalResultEvent = None  # type: ignore
    FunctionToolCallEvent = None  # type: ignore
    FunctionToolResultEvent = None  # type: ignore
    PartStartEvent = None  # type: ignore
    PartDeltaEvent = None  # type: ignore
    TextPartDelta = None  # type: ignore
    ThinkingPartDelta = None  # type: ignore
    OpenAIChatModel = None  # type: ignore
    OpenAIProvider = None  # type: ignore
    OpenAIModelProfile = None  # type: ignore


@dataclass
class AgentDependencies:
    """Agent 依赖注入"""
    reg_id: str | None = None


class PydanticAIAgent(RegReaderAgent):
    """基于 Pydantic AI v1.0+ 的 Agent 实现

    使用 MCPServerStdio 直接连接 RegReader MCP Server，
    MCP Server 的所有工具会自动暴露给 Agent。

    特性:
    - 自动 MCP 工具集成（通过 toolsets）
    - 消息历史管理（支持多轮对话）
    - 多模型支持（Anthropic/OpenAI/Ollama）
    - 依赖注入
    """

    def __init__(
        self,
        config: PydanticAgentConfig | RegReaderConfig | None = None,
        reg_id: str | None = None,
        model: str | None = None,
        mcp_config: MCPConnectionConfig | None = None,
        status_callback: StatusCallback | None = None,
    ):
        """初始化 Pydantic AI Agent

        Args:
            config: Agent 配置
            reg_id: 默认规程标识
            model: 模型名称
            mcp_config: MCP 连接配置
            status_callback: 状态回调
        """
        if not HAS_PYDANTIC_AI:
            raise ImportError(
                "Pydantic AI not installed or outdated. "
                "Please run: pip install 'pydantic-ai>=1.0.0'"
            )

        # 构建配置
        if config is None:
            config = PydanticAgentConfig()

        # 如果传入的是 RegReaderConfig，转换为 PydanticAgentConfig
        if not isinstance(config, PydanticAgentConfig):
            config = PydanticAgentConfig(
                reg_id=config.reg_id,
                enable_memory=config.enable_memory,
                enable_toc_cache=config.enable_toc_cache,
                prompt_mode=config.prompt_mode,
                mcp_config=config.mcp_config,
                status_callback=config.status_callback,
                model=config.model,
                system_prompt=config.system_prompt,
                max_iterations=config.max_iterations,
                timeout_seconds=config.timeout_seconds,
            )

        # 覆盖配置中的值
        if mcp_config is not None:
            config.mcp_config = mcp_config
        if status_callback is not None:
            config.status_callback = status_callback

        super().__init__(config=config, reg_id=reg_id, status_callback=status_callback)

        settings = get_settings()

        # 获取模型名称
        model_name = model or config.model or settings.llm_model_name

        # 检测是否为 Ollama 后端
        self._is_ollama = settings.is_ollama_backend()
        self._ollama_disable_streaming = settings.ollama_disable_streaming

        # 设置环境变量
        import os
        os.environ["OPENAI_API_KEY"] = settings.llm_api_key
        os.environ["OPENAI_BASE_URL"] = settings.llm_base_url

        # 根据后端类型创建模型
        if self._is_ollama:
            ollama_base = settings.llm_base_url
            if not ollama_base.endswith("/v1"):
                ollama_base = ollama_base.rstrip("/") + "/v1"

            self._ollama_http_client = httpx.AsyncClient(
                transport=httpx.AsyncHTTPTransport(),
            )

            ollama_model = OpenAIChatModel(
                model_name=model_name,
                provider=OpenAIProvider(
                    base_url=ollama_base,
                    api_key="ollama",
                    http_client=self._ollama_http_client,
                ),
                profile=OpenAIModelProfile(
                    openai_supports_strict_tool_definition=False,
                ),
            )
            self._model = ollama_model
            self._model_name = f"ollama:{model_name}"
        else:
            self._model = f"openai:{model_name}"
            self._model_name = self._model
            self._ollama_http_client = None

        # 获取 MCP 连接管理器
        self._mcp_manager = get_mcp_manager(config.mcp_config)

        # PageStore 实例
        self._page_store = PageStore(settings.pages_dir)
        self._regulations_cache: list[dict] | None = None

        # 创建 MCP Server 连接
        self._mcp_server = self._mcp_manager.get_pydantic_mcp_server()

        # 创建 Agent
        self._pydantic_agent = Agent(
            self._model,
            deps_type=AgentDependencies,
            toolsets=[self._mcp_server],
        )

        # 注册动态系统提示词
        @self._pydantic_agent.system_prompt(dynamic=True)
        def dynamic_system_prompt(ctx: RunContext[AgentDependencies]) -> str:
            return self._build_system_prompt()

        # 消息历史
        self._message_history: list = []

        # 工具调用记录
        self._tool_calls: list[dict] = []
        self._sources: list[str] = []
        self._tool_start_times: dict[str, float] = {}
        self._last_tool_end_time: float | None = None

        # 连接状态
        self._connected = False

        logger.info(
            f"PydanticAIAgent (v2) initialized: model={self._model_name}, "
            f"mcp_transport={self._mcp_manager.config.transport}"
        )

    @property
    def name(self) -> str:
        """Agent 名称"""
        return "PydanticAIAgent"

    @property
    def model(self) -> str:
        """使用的模型名称"""
        return self._model_name

    async def _create_agent(self) -> BaseAgent:
        """创建底层 agentex Agent

        PydanticAIAgent 直接使用 Pydantic AI，不通过 agentex 框架。
        """
        return None  # type: ignore

    def _get_regulations(self) -> list[dict]:
        """获取规程列表（带缓存）"""
        if self._regulations_cache is None:
            regulations = self._page_store.list_regulations()
            self._regulations_cache = [
                {
                    "reg_id": r.reg_id,
                    "title": r.title,
                    "keywords": r.keywords,
                    "scope": r.scope,
                    "description": r.description,
                }
                for r in regulations
            ]
        return self._regulations_cache

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        settings = get_settings()
        include_advanced = getattr(settings, "enable_advanced_tools", False)
        regulations = self._get_regulations()

        if self._config.prompt_mode == "full":
            base_prompt = get_full_prompt(include_advanced, regulations)
        elif self._config.prompt_mode == "simple":
            base_prompt = get_simple_prompt()
        else:
            base_prompt = get_optimized_prompt_with_domain(include_advanced, regulations)

        if self.reg_id:
            base_prompt += f"\n\n# 当前规程\n默认规程: {self.reg_id}"

        if self._memory:
            toc_hint = self._memory.get_toc_cache_hint()
            if toc_hint:
                base_prompt += toc_hint

            memory_context = self._memory.get_memory_context()
            if memory_context:
                base_prompt += f"\n\n{memory_context}"

        return base_prompt

    async def _ensure_connected(self) -> None:
        """确保 Agent 已连接"""
        if not self._connected:
            await self._pydantic_agent.__aenter__()
            self._connected = True

    def _create_event_stream_handler(self):
        """创建事件流处理器"""

        async def event_stream_handler(
            ctx: RunContext,
            event_stream: AsyncIterable[AgentStreamEvent],
        ):
            async for event in event_stream:
                if isinstance(event, PartDeltaEvent):
                    if isinstance(event.delta, TextPartDelta):
                        pass  # 文本增量
                    elif isinstance(event.delta, ThinkingPartDelta):
                        pass  # 思考增量

                elif isinstance(event, FunctionToolCallEvent):
                    tool_name = event.part.tool_name
                    tool_args = event.part.args
                    tool_call_id = event.part.tool_call_id or ""

                    now = time.time()
                    self._tool_start_times[tool_call_id] = now

                    if isinstance(tool_args, str):
                        try:
                            tool_input = json.loads(tool_args)
                        except json.JSONDecodeError:
                            tool_input = {"raw": tool_args}
                    else:
                        tool_input = tool_args if isinstance(tool_args, dict) else {}

                    self._tool_calls.append({
                        "name": tool_name,
                        "input": tool_input,
                        "tool_call_id": tool_call_id,
                    })

                    await self._callback.on_event(
                        EventAdapter.create_tool_start_event(tool_name, tool_input)
                    )

                elif isinstance(event, FunctionToolResultEvent):
                    tool_call_id = event.tool_call_id or ""
                    result_content = event.result.content if hasattr(event.result, "content") else event.result

                    start_time = self._tool_start_times.pop(tool_call_id, None)
                    now = time.time()
                    duration_ms = (now - start_time) * 1000 if start_time else 0

                    self._last_tool_end_time = now

                    tool_name = "unknown"
                    for tc in reversed(self._tool_calls):
                        if tc.get("tool_call_id") == tool_call_id:
                            tool_name = tc.get("name", "unknown")
                            tc["output"] = result_content
                            break

                    await self._callback.on_event(
                        EventAdapter.create_tool_end_event(tool_name, result_content, duration_ms)
                    )

                    self._extract_sources_from_content(result_content)
                    self._update_memory(tool_name, result_content)

        return event_stream_handler

    async def chat(
        self,
        message: str,
        session_id: str | None = None,
    ) -> AgentResponse:
        """与 Agent 对话"""
        await self._ensure_connected()

        # 获取或创建会话
        session = self._session_manager.get_or_create(session_id)
        session.reset_per_query()

        # 重置单次查询状态
        self._tool_calls = []
        self._sources = []
        self._tool_start_times = {}
        self._last_tool_end_time = None

        deps = AgentDependencies(reg_id=self.reg_id)
        event_handler = self._create_event_stream_handler()

        start_time = time.time()

        await self._callback.on_event(EventAdapter.create_thinking_event(start=True))

        try:
            use_streaming = not (self._is_ollama and self._ollama_disable_streaming)

            if use_streaming:
                result = await self._pydantic_agent.run(
                    message,
                    deps=deps,
                    message_history=self._message_history if self._message_history else None,
                    event_stream_handler=event_handler,
                )
            else:
                result = await self._pydantic_agent.run(
                    message,
                    deps=deps,
                    message_history=self._message_history if self._message_history else None,
                )

            self._message_history = result.all_messages()

            await self._callback.on_event(EventAdapter.create_thinking_event(start=False))

            duration_ms = (time.time() - start_time) * 1000

            await self._callback.on_event(
                EventAdapter.create_response_complete_event(
                    content=result.output,
                    sources=list(set(self._sources)),
                )
            )

            # 同步到会话
            for tc in self._tool_calls:
                session.add_tool_call(
                    name=tc.get("name", "unknown"),
                    input_data=tc.get("input", {}),
                    output=tc.get("output"),
                )
            for source in self._sources:
                session.add_source(source)

            return AgentResponse(
                content=result.output,
                sources=list(set(self._sources)),
                tool_calls=self._tool_calls,
            )

        except Exception as e:
            logger.exception(f"Agent error: {e}")
            await self._callback.on_event(EventAdapter.create_thinking_event(start=False))

            return AgentResponse(
                content=f"查询失败: {str(e)}",
                sources=list(set(self._sources)),
                tool_calls=self._tool_calls,
            )

    def _extract_sources_from_content(self, content: Any) -> None:
        """从内容中提取来源信息"""
        if content is None:
            return

        if isinstance(content, dict):
            if "source" in content and content["source"]:
                self._sources.append(str(content["source"]))

            for key, value in content.items():
                if key != "source":
                    self._extract_sources_from_content(value)

        elif isinstance(content, list):
            for item in content:
                self._extract_sources_from_content(item)

        elif isinstance(content, str):
            try:
                parsed = json.loads(content)
                self._extract_sources_from_content(parsed)
            except (json.JSONDecodeError, TypeError):
                pass

    def _update_memory(self, tool_name: str, result: Any) -> None:
        """更新记忆系统"""
        if not self._memory:
            return

        if isinstance(result, str):
            try:
                result = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return

        if not isinstance(result, dict):
            return

        if tool_name == "get_toc":
            reg_id = result.get("reg_id", self.reg_id)
            if reg_id:
                self._memory.cache_toc(reg_id, result)

        elif tool_name == "smart_search":
            results = result.get("result") or result.get("results", [])
            self._memory.add_search_results(results, self.reg_id)

    async def reset(self, session_id: str | None = None) -> None:
        """重置对话历史"""
        self._session_manager.reset(session_id)
        self._message_history = []
        self._tool_calls = []
        self._sources = []
        self._tool_start_times = {}
        self._last_tool_end_time = None
        if self._memory:
            self._memory.clear_query_context()

    async def close(self) -> None:
        """关闭 Agent 连接"""
        if self._connected:
            await self._pydantic_agent.__aexit__(None, None, None)
            self._connected = False

        if self._ollama_http_client is not None:
            await self._ollama_http_client.aclose()
            self._ollama_http_client = None

    async def __aenter__(self) -> "PydanticAIAgent":
        """异步上下文管理器入口"""
        await self._ensure_connected()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        await self.close()
