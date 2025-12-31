"""Pydantic AI Agent 实现

使用 Pydantic AI v1.0+ 框架实现 GridCode Agent。
通过 MCPServerStdio 直接连接 GridCode MCP Server，无需手动注册工具。

架构:
    PydanticAIAgent
        └── MCPServerStdio (toolsets)
                └── GridCode MCP Server (stdio)
                        └── PageStore (页面数据)
"""

import json
import time
from collections.abc import AsyncIterable
from dataclasses import dataclass
from typing import Any

from loguru import logger

from grid_code.agents.base import AgentResponse, BaseGridCodeAgent
from grid_code.agents.callbacks import NullCallback, StatusCallback
from grid_code.agents.events import (
    AgentEvent,
    AgentEventType,
    iteration_event,
    response_complete_event,
    text_delta_event,
    thinking_event,
    tool_end_event,
    tool_start_event,
)
from grid_code.agents.mcp_connection import MCPConnectionConfig, get_mcp_manager
from grid_code.agents.prompts import SYSTEM_PROMPT
from grid_code.agents.result_parser import parse_tool_result
from grid_code.config import get_settings

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
    logger.warning("pydantic-ai not installed or outdated. Run: pip install 'pydantic-ai>=1.0.0'")


@dataclass
class AgentDependencies:
    """Agent 依赖注入

    Pydantic AI 通过 RunContext 传递依赖到工具和系统提示中。
    """

    reg_id: str | None = None
    """默认规程标识"""


class PydanticAIAgent(BaseGridCodeAgent):
    """基于 Pydantic AI v1.0+ 的 Agent 实现

    使用 MCPServerStdio 直接连接 GridCode MCP Server，
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

        # 对于 Pydantic AI，统一使用 openai 兼容接口
        # 因为大多数国产模型都提供 OpenAI 兼容接口
        self._model_name = f"openai:{model_name}"
        logger.debug(f"Using model: {self._model_name}, provider: {provider}")

        # 设置环境变量（Pydantic AI 从环境变量读取）
        import os

        os.environ["OPENAI_API_KEY"] = settings.llm_api_key
        os.environ["OPENAI_BASE_URL"] = settings.llm_base_url

        # 获取 MCP 连接管理器
        self._mcp_manager = get_mcp_manager(mcp_config)

        # 创建 MCP Server 连接（支持 stdio 和 SSE 模式）
        self._mcp_server = self._mcp_manager.get_pydantic_mcp_server()

        # 创建 Agent（带 MCP toolsets）
        self._agent = Agent(
            self._model_name,
            deps_type=AgentDependencies,
            system_prompt=self._build_system_prompt(),
            toolsets=[self._mcp_server],
        )

        # 消息历史（用于多轮对话）
        self._message_history: list[ModelMessage] = []

        # 工具调用记录（单次查询）
        self._tool_calls: list[dict] = []
        self._sources: list[str] = []
        self._tool_start_times: dict[str, float] = {}  # tool_call_id -> start_time

        # 连接状态
        self._connected = False

        # 状态回调
        self._callback = status_callback or NullCallback()

        logger.info(
            f"PydanticAIAgent initialized: model={self._model_name}, "
            f"mcp_transport={self._mcp_manager.config.transport}"
        )

    def _build_system_prompt(self) -> str:
        """构建系统提示词

        如果指定了 reg_id，则添加上下文限定。
        """
        base_prompt = SYSTEM_PROMPT

        if self.reg_id:
            context = (
                f"\n\n# 当前规程上下文\n"
                f"默认规程标识: {self.reg_id}\n"
                f"调用工具时如未指定 reg_id，请使用此默认值。"
            )
            return base_prompt + context

        return base_prompt

    def _create_event_stream_handler(self):
        """创建事件流处理器

        返回一个异步函数，用于处理 Pydantic AI 的工具调用事件。
        通过 event_stream_handler 参数传递给 agent.run()。

        增强功能：
        - 追踪思考耗时（从上一工具结束到本工具开始）
        - 解析详细结果摘要（结果类型、章节数、页码、内容预览）
        """
        # 使用闭包变量追踪上一工具结束时间
        last_tool_end_time: float | None = None

        async def event_stream_handler(
            ctx: RunContext,
            event_stream: AsyncIterable[AgentStreamEvent],
        ):
            nonlocal last_tool_end_time

            async for event in event_stream:
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

                    now = time.time()

                    # 计算思考耗时（从上一工具结束到本工具开始）
                    thinking_duration_ms = None
                    if last_tool_end_time is not None:
                        thinking_duration_ms = (now - last_tool_end_time) * 1000
                        logger.debug(f"[EventStream] thinking_duration_ms={thinking_duration_ms:.1f}")

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

                    # 记录工具调用（带 tool_call_id 以便后续匹配）
                    self._tool_calls.append({
                        "name": tool_name,
                        "input": tool_input,
                        "tool_call_id": tool_call_id,
                        "thinking_duration_ms": thinking_duration_ms,
                    })

                    # 发送工具调用开始事件
                    await self._callback.on_event(
                        tool_start_event(tool_name, tool_input, tool_call_id)
                    )

                elif isinstance(event, FunctionToolResultEvent):
                    # 工具调用完成
                    tool_call_id = event.tool_call_id or ""

                    logger.debug(f"[EventStream] CALL_RESULT: id={tool_call_id}, stored_ids={list(self._tool_start_times.keys())}")

                    # 计算执行耗时
                    start_time = self._tool_start_times.pop(tool_call_id, None)
                    now = time.time()
                    if start_time is not None:
                        duration_ms = (now - start_time) * 1000
                        logger.debug(f"[EventStream] duration_ms={duration_ms:.1f}")
                    else:
                        duration_ms = None
                        logger.debug(f"[EventStream] No start time for tool_call_id={tool_call_id}")

                    # 记录工具结束时间（用于计算下一个工具的思考耗时）
                    last_tool_end_time = now

                    # 从结果中提取信息
                    result_content = event.result.content if hasattr(event.result, "content") else event.result

                    # 获取工具名称和参数
                    tool_name = "unknown"
                    tool_input = {}
                    thinking_duration_ms = None
                    for tc in reversed(self._tool_calls):
                        if tc.get("tool_call_id") == tool_call_id:
                            tool_name = tc.get("name", "unknown")
                            tool_input = tc.get("input", {})
                            thinking_duration_ms = tc.get("thinking_duration_ms")
                            # 更新工具调用记录的输出
                            tc["output"] = result_content
                            break

                    # 使用结果解析器提取详细摘要
                    summary = parse_tool_result(tool_name, result_content)

                    # 发送工具调用完成事件（带详细摘要）
                    await self._callback.on_event(
                        tool_end_event(
                            tool_name=tool_name,
                            tool_id=tool_call_id,
                            duration_ms=duration_ms,
                            result_count=summary.result_count,
                            tool_input=tool_input,
                            # 详细模式新增字段
                            result_type=summary.result_type,
                            chapter_count=summary.chapter_count,
                            page_sources=summary.page_sources,
                            content_preview=summary.content_preview,
                            thinking_duration_ms=thinking_duration_ms,
                        )
                    )

                    # 提取来源信息
                    self._extract_sources_from_content(result_content)

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

        # 创建依赖
        deps = AgentDependencies(reg_id=self.reg_id)

        # 创建事件流处理器（用于实时工具调用事件）
        event_handler = self._create_event_stream_handler()

        # 记录开始时间
        start_time = time.time()

        # 发送思考开始事件
        await self._callback.on_event(thinking_event(start=True))

        try:
            # 运行 Agent（传入消息历史和事件处理器）
            result = await self._agent.run(
                message,
                deps=deps,
                message_history=self._message_history if self._message_history else None,
                event_stream_handler=event_handler,
            )

            # 更新消息历史
            self._message_history = result.all_messages()

            # 发送思考结束事件
            await self._callback.on_event(thinking_event(start=False))

            # 计算总耗时
            duration_ms = (time.time() - start_time) * 1000

            # 发送响应完成事件
            await self._callback.on_event(
                response_complete_event(
                    total_tool_calls=len(self._tool_calls),
                    total_sources=len(set(self._sources)),
                    duration_ms=duration_ms,
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

    async def reset(self) -> None:
        """重置对话历史

        清空消息历史，开始新的对话。
        """
        self._message_history = []
        self._tool_calls = []
        self._sources = []
        self._tool_start_times = {}
        logger.debug("Conversation history reset")

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

        断开与 MCP Server 的连接。
        """
        if self._connected:
            await self._agent.__aexit__(None, None, None)
            self._connected = False
            logger.debug("Agent disconnected from MCP Server")

    async def __aenter__(self) -> "PydanticAIAgent":
        """异步上下文管理器入口"""
        await self._ensure_connected()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        await self.close()
