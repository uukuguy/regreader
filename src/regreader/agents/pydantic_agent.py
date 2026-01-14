"""Pydantic AI Agent 实现

使用 Pydantic AI v1.0+ 框架实现 RegReader Agent。
通过 MCPServerStdio 直接连接 RegReader MCP Server，无需手动注册工具。

架构:
    PydanticAIAgent
        └── MCPServerStdio (toolsets)
                └── RegReader MCP Server (stdio)
                        └── PageStore (页面数据)
"""

import json
import time
from collections.abc import AsyncIterable
from dataclasses import dataclass
from typing import Any

from loguru import logger

from regreader.agents.base import AgentResponse, BaseRegReaderAgent
from regreader.agents.callbacks import NullCallback, StatusCallback
from regreader.agents.events import (
    AgentEvent,
    AgentEventType,
    answer_generation_end_event,
    iteration_event,
    response_complete_event,
    text_delta_event,
    thinking_event,
    tool_end_event,
    tool_start_event,
)
from regreader.agents.llm_timing import LLMTimingCollector
from regreader.agents.mcp_connection import MCPConnectionConfig, get_mcp_manager
from regreader.agents.memory import AgentMemory, ContentChunk
from regreader.agents.prompts import (
    get_full_prompt,
    get_optimized_prompt_with_domain,
    get_simple_prompt,
)
from regreader.agents.result_parser import parse_tool_result
from regreader.config import get_settings
from regreader.storage import PageStore

# Pydantic AI imports
try:
    from pydantic_ai import Agent, RunContext
    from pydantic_ai.mcp import MCPServerStdio
    from pydantic_ai.messages import (
        AgentStreamEvent,
        FunctionToolCallEvent,
        FunctionToolResultEvent,
        ModelMessage,
        PartDeltaEvent,
        TextPartDelta,
        ThinkingPartDelta,
    )
    # Ollama 支持
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
    FunctionToolCallEvent = None  # type: ignore
    FunctionToolResultEvent = None  # type: ignore
    OpenAIChatModel = None  # type: ignore
    OpenAIProvider = None  # type: ignore
    OpenAIModelProfile = None  # type: ignore
    logger.warning("pydantic-ai not installed or outdated. Run: pip install 'pydantic-ai>=1.0.0'")


@dataclass
class AgentDependencies:
    """Agent 依赖注入

    Pydantic AI 通过 RunContext 传递依赖到工具和系统提示中。
    """

    reg_id: str | None = None
    """默认规程标识"""


class PydanticAIAgent(BaseRegReaderAgent):
    """基于 Pydantic AI v1.0+ 的 Agent 实现

    使用 MCPServerStdio 直接连接 RegReader MCP Server，
    MCP Server 的所有工具会自动暴露给 Agent。

    特性:
    - 自动 MCP 工具集成（通过 toolsets）
    - 消息历史管理（支持多轮对话）
    - 多模型支持（Anthropic/OpenAI/Google）
    - 依赖注入

    Usage:
        async with PydanticAIAgent(reg_id="angui_2024") as agent:
            response = await agent.chat("母线失压如何处理？")
            print(response.content)

            # 多轮对话
            response2 = await agent.chat("还有其他注意事项吗？")
    """

    def __init__(
        self,
        reg_id: str | None = None,
        model: str | None = None,
        mcp_config: MCPConnectionConfig | None = None,
        status_callback: StatusCallback | None = None,
    ):
        """初始化 Pydantic AI Agent

        Args:
            reg_id: 默认规程标识（可选）
            model: 模型名称，格式为 'provider:model'
                   如 'anthropic:claude-sonnet-4-20250514'
                   默认使用配置文件中的 default_model
            mcp_config: MCP 连接配置（可选，默认从全局配置创建）
            status_callback: 状态回调（可选），用于实时输出 Agent 运行状态
        """
        super().__init__(reg_id)

        if not HAS_PYDANTIC_AI:
            raise ImportError(
                "Pydantic AI not installed or outdated. "
                "Please run: pip install 'pydantic-ai>=1.0.0'"
            )

        settings = get_settings()

        # 获取提供商和模型名称
        provider = settings.get_llm_provider()
        model_name = model or settings.llm_model_name

        # 检测是否为 Ollama 后端
        self._is_ollama = settings.is_ollama_backend()
        self._ollama_disable_streaming = settings.ollama_disable_streaming

        # 设置环境变量（Pydantic AI 从环境变量读取）
        import os

        os.environ["OPENAI_API_KEY"] = settings.llm_api_key
        os.environ["OPENAI_BASE_URL"] = settings.llm_base_url

        # 根据后端类型创建模型
        if self._is_ollama:
            # Ollama 专用配置：使用 OpenAIChatModel + OpenAIProvider + 自定义 httpx client
            # 关键修复：httpx 默认配置与 Ollama 不兼容，需要显式创建 transport
            # 参考：https://github.com/encode/httpx/issues/XXX
            ollama_base = settings.llm_base_url
            if not ollama_base.endswith("/v1"):
                ollama_base = ollama_base.rstrip("/") + "/v1"

            # 创建 LLM 时间收集器（用于精确测量 API 调用时间）
            self._timing_collector = LLMTimingCollector(callback=status_callback)

            # 创建自定义 httpx client（解决 502 问题 + 注入时间收集 hooks）
            self._ollama_http_client = httpx.AsyncClient(
                transport=httpx.AsyncHTTPTransport(),
                event_hooks={
                    "request": [self._timing_collector.on_request],
                    "response": [self._timing_collector.on_response],
                },
            )

            ollama_model = OpenAIChatModel(
                model_name=model_name,
                provider=OpenAIProvider(
                    base_url=ollama_base,
                    api_key="ollama",  # Ollama 不需要真实 API key
                    http_client=self._ollama_http_client,
                ),
                profile=OpenAIModelProfile(
                    openai_supports_strict_tool_definition=False,
                ),
            )
            self._model = ollama_model
            self._model_name = f"ollama:{model_name}"
            logger.info(f"Using Ollama backend: {model_name}, base_url={ollama_base}")
        else:
            # 其他 OpenAI 兼容后端
            self._model = f"openai:{model_name}"
            self._model_name = self._model
            self._ollama_http_client = None
            self._timing_collector = None  # 非 Ollama 后端暂不支持 API 时间测量
            logger.debug(f"Using model: {self._model_name}, provider: {provider}")

        # 获取 MCP 连接管理器
        self._mcp_manager = get_mcp_manager(mcp_config)

        # PageStore 实例（用于获取规程列表）
        self._page_store = PageStore(settings.pages_dir)
        # 规程列表缓存（避免重复读取）
        self._regulations_cache: list[dict] | None = None

        # 创建 MCP Server 连接（支持 stdio 和 SSE 模式）
        self._mcp_server = self._mcp_manager.get_pydantic_mcp_server()

        # 创建 Agent（带 MCP toolsets）
        self._agent = Agent(
            self._model,
            deps_type=AgentDependencies,
            toolsets=[self._mcp_server],
        )

        # 使用装饰器注册动态系统提示词
        # dynamic=True 确保每次运行时重新构建（包含记忆上下文）
        @self._agent.system_prompt(dynamic=True)
        def dynamic_system_prompt(ctx: RunContext[AgentDependencies]) -> str:
            return self._build_system_prompt()

        # 消息历史（用于多轮对话）
        self._message_history: list[ModelMessage] = []

        # 记忆系统（目录缓存 + 相关内容记忆）
        self._enable_memory = settings.enable_agent_memory
        self._memory = AgentMemory() if self._enable_memory else None

        # 工具调用记录（单次查询）
        self._tool_calls: list[dict] = []
        self._sources: list[str] = []
        self._tool_start_times: dict[str, float] = {}  # tool_call_id -> start_time
        self._last_tool_end_time: float | None = None  # 最后一个工具结束时间

        # 连接状态
        self._connected = False

        # 状态回调
        self._callback = status_callback or NullCallback()

        logger.info(
            f"PydanticAIAgent initialized: model={self._model_name}, "
            f"mcp_transport={self._mcp_manager.config.transport}"
        )

    def _get_regulations(self) -> list[dict]:
        """获取规程列表（带缓存）

        从 PageStore 读取所有规程信息，转换为字典格式供 Prompt 使用。
        使用缓存避免重复读取文件系统。

        Returns:
            规程信息列表，每个元素包含 reg_id, title, keywords, scope 等字段
        """
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
            logger.debug(f"加载规程列表: {len(self._regulations_cache)} 个")
        return self._regulations_cache

    def _build_system_prompt(self) -> str:
        """构建系统提示词

        根据配置选择不同版本的提示词：
        - full: 完整版（向后兼容）
        - optimized: 优化版（默认，减少 token 消耗）
        - simple: 最简版（最快响应）

        同时注入规程列表和记忆上下文（目录缓存提示 + 已获取的相关内容）
        """
        settings = get_settings()
        include_advanced = getattr(settings, "enable_advanced_tools", False)

        # 获取规程列表用于动态生成提示词
        regulations = self._get_regulations()

        if settings.prompt_mode == "full":
            base_prompt = get_full_prompt(include_advanced, regulations)
        elif settings.prompt_mode == "simple":
            base_prompt = get_simple_prompt()  # simple 模式不注入规程列表
        else:  # optimized
            base_prompt = get_optimized_prompt_with_domain(include_advanced, regulations)

        if self.reg_id:
            base_prompt += f"\n\n# 当前规程\n默认规程: {self.reg_id}"

        # 注入目录缓存提示（仅在启用记忆时）
        if self._memory:
            toc_hint = self._memory.get_toc_cache_hint()
            if toc_hint:
                base_prompt += toc_hint

            # 注入已获取的相关内容
            memory_context = self._memory.get_memory_context()
            if memory_context:
                base_prompt += f"\n\n{memory_context}"

        return base_prompt

    def _create_event_stream_handler(self):
        """创建事件流处理器

        返回一个异步函数，用于处理 Pydantic AI 的工具调用事件。
        通过 event_stream_handler 参数传递给 agent.run()。

        增强功能：
        - 追踪思考耗时（从上一工具结束到本工具开始）
        - 解析详细结果摘要（结果类型、章节数、页码、内容预览）
        """

        async def event_stream_handler(
            ctx: RunContext,
            event_stream: AsyncIterable[AgentStreamEvent],
        ):
            async for event in event_stream:
                # DEBUG: 记录所有事件类型，帮助排查漏记问题
                event_type = type(event).__name__
                # logger.debug(f"[EventStream] Event received: {event_type}")

                # 处理文本增量事件（流式输出）
                if isinstance(event, PartDeltaEvent):
                    if isinstance(event.delta, TextPartDelta):
                        # 文本增量 - 模型生成的回复内容
                        delta_text = event.delta.content_delta
                        if delta_text:
                            await self._callback.on_event(
                                text_delta_event(delta_text)
                            )
                    elif isinstance(event.delta, ThinkingPartDelta):
                        # 思考增量 - 模型的推理过程（如 Claude 的 thinking）
                        thinking_text = event.delta.content_delta
                        if thinking_text:
                            await self._callback.on_event(
                                AgentEvent(
                                    event_type=AgentEventType.THINKING_DELTA,
                                    data={"delta": thinking_text}
                                )
                            )

                elif isinstance(event, FunctionToolCallEvent):
                    # 工具调用开始
                    tool_name = event.part.tool_name
                    tool_args = event.part.args
                    tool_call_id = event.part.tool_call_id or ""

                    logger.debug(f"[EventStream] CALL_START: {tool_name}, id={tool_call_id}")
                    # print(f"[DEBUG pydantic_agent.py] CALL_START: {tool_name}, id={tool_call_id}")

                    now = time.time()

                    # 计算思考耗时（从上一工具结束到本工具开始）
                    thinking_duration_ms = None
                    if self._last_tool_end_time is not None:
                        thinking_duration_ms = (now - self._last_tool_end_time) * 1000

                    # 获取 API 调用统计（自上一步骤以来的累计）
                    api_duration_ms = None
                    api_call_count = None
                    if self._timing_collector:
                        step_metrics = self._timing_collector.get_step_metrics()
                        if step_metrics.api_calls > 0:
                            api_duration_ms = step_metrics.api_duration_ms
                            api_call_count = step_metrics.api_calls
                            logger.debug(
                                f"[EventStream] Thinking phase API: "
                                f"{api_call_count} calls, {api_duration_ms:.0f}ms"
                            )
                        # 重置步骤统计，为下一步骤准备
                        self._timing_collector.start_step()

                    # 记录开始时间
                    self._tool_start_times[tool_call_id] = now

                    # 解析参数
                    if isinstance(tool_args, str):
                        try:
                            tool_input = json.loads(tool_args)
                        except json.JSONDecodeError:
                            tool_input = {"raw": tool_args}
                    else:
                        tool_input = tool_args if isinstance(tool_args, dict) else {}

                    # 记录工具调用（包含 API 统计）
                    self._tool_calls.append({
                        "name": tool_name,
                        "input": tool_input,
                        "tool_call_id": tool_call_id,
                        "thinking_duration_ms": thinking_duration_ms,
                        "api_duration_ms": api_duration_ms,
                        "api_call_count": api_call_count,
                    })

                    # 发送工具调用开始事件
                    await self._callback.on_event(
                        tool_start_event(tool_name, tool_input, tool_call_id)
                    )

                elif isinstance(event, FunctionToolResultEvent):
                    # 工具调用完成
                    tool_call_id = event.tool_call_id or ""

                    # 从结果中提取信息
                    result_content = event.result.content if hasattr(event.result, "content") else event.result

                    # DEBUG: 记录完整的工具响应信息
                    # print(f"[DEBUG pydantic_agent.py] PostToolUse called: {tool_call_id}")
                    # print(f"[DEBUG pydantic_agent.py] result_content type: {type(result_content).__name__}")
                    # print(f"[DEBUG pydantic_agent.py] result_content repr: {repr(result_content)[:300]}")

                    # 计算执行耗时
                    start_time = self._tool_start_times.pop(tool_call_id, None)
                    now = time.time()
                    duration_ms = (now - start_time) * 1000 if start_time else None

                    # 记录工具结束时间（使用实例变量，供答案生成阶段使用）
                    self._last_tool_end_time = now

                    # 获取工具名称和参数（包含 API 统计）
                    tool_name = "unknown"
                    tool_input = {}
                    thinking_duration_ms = None
                    api_duration_ms = None
                    api_call_count = None
                    for tc in reversed(self._tool_calls):
                        if tc.get("tool_call_id") == tool_call_id:
                            tool_name = tc.get("name", "unknown")
                            tool_input = tc.get("input", {})
                            thinking_duration_ms = tc.get("thinking_duration_ms")
                            api_duration_ms = tc.get("api_duration_ms")
                            api_call_count = tc.get("api_call_count")
                            tc["output"] = result_content
                            break

                    # 使用结果解析器提取详细摘要
                    summary = parse_tool_result(tool_name, result_content)

                    # 发送工具调用完成事件（包含 API 统计）
                    await self._callback.on_event(
                        tool_end_event(
                            tool_name=tool_name,
                            tool_id=tool_call_id,
                            duration_ms=duration_ms,
                            result_count=summary.result_count,
                            tool_input=tool_input,
                            result_type=summary.result_type,
                            chapter_count=summary.chapter_count,
                            page_sources=summary.page_sources,
                            content_preview=summary.content_preview,
                            thinking_duration_ms=thinking_duration_ms,
                            api_duration_ms=api_duration_ms,
                            api_call_count=api_call_count,
                        )
                    )

                    # 提取来源信息并更新记忆
                    self._extract_sources_from_content(result_content)
                    self._update_memory(tool_name, result_content)

                elif event_type == "ModelResponseEvent":
                    # 检查是否有工具调用但在 FunctionToolCallEvent 中没捕捉到
                    if hasattr(event, "model_response") and hasattr(event.model_response, "parts"):
                        for part in event.model_response.parts:
                            if hasattr(part, "tool_name"):
                                logger.debug(f"[EventStream] Found ToolCall in ModelResponse: {part.tool_name}")

        return event_stream_handler

    @property
    def name(self) -> str:
        return "PydanticAIAgent"

    @property
    def model(self) -> str:
        return self._model_name

    async def _ensure_connected(self) -> None:
        """确保 Agent 已连接到 MCP Server"""
        if not self._connected:
            await self._agent.__aenter__()
            self._connected = True
            logger.debug("Agent connected to MCP Server")

    async def chat(self, message: str) -> AgentResponse:
        """与 Agent 对话

        支持多轮对话，自动维护消息历史。

        Args:
            message: 用户消息

        Returns:
            AgentResponse 包含回答内容、来源引用和工具调用记录
        """
        # 确保已连接
        await self._ensure_connected()

        # 重置单次查询的临时状态
        self._tool_calls = []
        self._sources = []
        self._tool_start_times = {}
        self._last_tool_end_time = None  # 重置最后工具结束时间

        # 创建依赖
        deps = AgentDependencies(reg_id=self.reg_id)

        # 创建事件流处理器（用于实时工具调用事件）
        event_handler = self._create_event_stream_handler()

        # 记录开始时间
        start_time = time.time()

        # 发送思考开始事件
        await self._callback.on_event(thinking_event(start=True))

        try:
            # Ollama 流式策略：
            # 1. 如果配置了禁用流式，直接使用非流式模式
            # 2. 否则尝试流式，失败时降级到非流式
            use_streaming = not (self._is_ollama and self._ollama_disable_streaming)

            if use_streaming:
                try:
                    # 尝试流式调用
                    result = await self._agent.run(
                        message,
                        deps=deps,
                        message_history=self._message_history if self._message_history else None,
                        event_stream_handler=event_handler,
                    )
                except Exception as streaming_error:
                    # Ollama 流式失败时降级到非流式
                    if self._is_ollama:
                        logger.warning(
                            f"Ollama streaming failed, falling back to non-streaming: {streaming_error}"
                        )
                        result = await self._agent.run(
                            message,
                            deps=deps,
                            message_history=self._message_history if self._message_history else None,
                            # 不传 event_stream_handler，使用非流式模式
                        )
                    else:
                        raise
            else:
                # Ollama 禁用流式时，直接使用非流式模式
                logger.debug("Ollama streaming disabled, using non-streaming mode")
                result = await self._agent.run(
                    message,
                    deps=deps,
                    message_history=self._message_history if self._message_history else None,
                )

            # 更新消息历史
            self._message_history = result.all_messages()

            # 发送思考结束事件
            await self._callback.on_event(thinking_event(start=False))

            # 计算总耗时
            end_time = time.time()
            duration_ms = (end_time - start_time) * 1000

            # 获取最后一步的 API 统计（生成最终答案时的 LLM 调用）
            final_api_duration_ms = None
            final_api_call_count = None
            if self._timing_collector:
                step_metrics = self._timing_collector.get_step_metrics()
                if step_metrics.api_calls > 0:
                    final_api_duration_ms = step_metrics.api_duration_ms
                    final_api_call_count = step_metrics.api_calls

            # 如果有工具调用，发送答案生成事件
            # 这表示最后一轮 LLM 调用（生成最终答案）的时间统计
            if self._tool_calls and self._last_tool_end_time is not None:
                answer_thinking_ms = (end_time - self._last_tool_end_time) * 1000
                await self._callback.on_event(
                    answer_generation_end_event(
                        thinking_duration_ms=answer_thinking_ms,
                        api_duration_ms=final_api_duration_ms,
                        api_call_count=final_api_call_count,
                    )
                )

            # 发送响应完成事件
            await self._callback.on_event(
                response_complete_event(
                    total_tool_calls=len(self._tool_calls),
                    total_sources=len(set(self._sources)),
                    duration_ms=duration_ms,
                    final_api_duration_ms=final_api_duration_ms,
                    final_api_call_count=final_api_call_count,
                )
            )

            return AgentResponse(
                content=result.output,
                sources=list(set(self._sources)),
                tool_calls=self._tool_calls,
            )

        except Exception as e:
            logger.exception(f"Agent error: {e}")

            # 发送思考结束事件（即使出错）
            await self._callback.on_event(thinking_event(start=False))

            return AgentResponse(
                content=f"查询失败: {str(e)}",
                sources=list(set(self._sources)),
                tool_calls=self._tool_calls,
            )

    def _extract_tool_calls_and_sources(self, result: Any) -> None:
        """从 Agent 结果中提取工具调用和来源信息

        Args:
            result: Agent.run() 返回的结果
        """
        # 遍历所有消息，提取工具调用
        for msg in result.all_messages():
            # ModelResponse 包含工具调用
            if hasattr(msg, "parts"):
                for part in msg.parts:
                    # ToolCallPart
                    if hasattr(part, "tool_name") and hasattr(part, "args"):
                        self._tool_calls.append({
                            "name": part.tool_name,
                            "input": part.args if isinstance(part.args, dict) else {},
                        })

                    # ToolReturnPart - 包含工具返回结果
                    if hasattr(part, "content") and hasattr(part, "tool_name"):
                        # 尝试从返回内容中提取来源
                        self._extract_sources_from_content(part.content)

                        # 更新最后一个同名工具调用的输出
                        for tc in reversed(self._tool_calls):
                            if tc["name"] == part.tool_name and "output" not in tc:
                                tc["output"] = part.content
                                break

    def _extract_sources_from_content(self, content: Any) -> None:
        """从内容中递归提取来源信息

        Args:
            content: 工具返回的内容（可能是字符串、字典或列表）
        """
        if content is None:
            return

        if isinstance(content, dict):
            # 检查 source 字段
            if "source" in content and content["source"]:
                self._sources.append(str(content["source"]))

            # 递归处理嵌套
            for key, value in content.items():
                if key != "source":
                    self._extract_sources_from_content(value)

        elif isinstance(content, list):
            for item in content:
                self._extract_sources_from_content(item)

        elif isinstance(content, str):
            # 尝试解析 JSON
            try:
                parsed = json.loads(content)
                self._extract_sources_from_content(parsed)
            except (json.JSONDecodeError, TypeError):
                pass

    def _update_memory(self, tool_name: str, result: Any) -> None:
        """根据工具结果更新记忆系统

        Args:
            tool_name: 工具名称
            result: 工具返回结果
        """
        # 记忆系统未启用时跳过
        if not self._memory:
            return

        # 解析 JSON 字符串
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return

        if not isinstance(result, dict):
            return

        if tool_name == "get_toc":
            # 缓存目录
            reg_id = result.get("reg_id", self.reg_id)
            if reg_id:
                self._memory.cache_toc(reg_id, result)

        elif tool_name == "smart_search":
            # 提取搜索结果（兼容 "result" 和 "results"）
            results = result.get("result") or result.get("results", [])
            self._memory.add_search_results(results)

        elif tool_name == "read_page_range":
            # 记录页面内容摘要
            content = result.get("content_markdown") or result.get("content")
            source = result.get("source", "")
            if content and source:
                self._memory.add_page_content(content, source)

        elif tool_name == "read_chapter_content":
            # 记录章节内容摘要
            content = result.get("content") or result.get("content_markdown")
            source = result.get("source", "")
            if content and source:
                self._memory.add_page_content(content, source, relevance=0.85)

    async def reset(self) -> None:
        """重置对话历史

        清空消息历史和记忆，开始新的对话。
        """
        self._message_history = []
        self._tool_calls = []
        self._sources = []
        self._tool_start_times = {}
        self._last_tool_end_time = None
        if self._memory:
            self._memory.reset()
        if self._timing_collector:
            self._timing_collector.reset()
        logger.debug("Conversation history and memory reset")

    def get_message_count(self) -> int:
        """获取当前消息历史数量

        Returns:
            消息数量
        """
        return len(self._message_history)

    def get_message_history(self) -> list[ModelMessage]:
        """获取消息历史

        Returns:
            消息历史列表（只读副本）
        """
        return list(self._message_history)

    async def close(self) -> None:
        """关闭 Agent 连接

        断开与 MCP Server 的连接，并清理资源。
        """
        if self._connected:
            await self._agent.__aexit__(None, None, None)
            self._connected = False
            logger.debug("Agent disconnected from MCP Server")

        # 关闭 Ollama httpx client
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
