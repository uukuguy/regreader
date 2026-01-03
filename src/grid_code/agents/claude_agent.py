"""Claude Agent SDK 实现

使用 Claude Agent SDK 实现 GridCode Agent。
https://github.com/anthropics/claude-agent-sdk-python
"""

import time
from typing import Any

from loguru import logger

from grid_code.agents.base import AgentResponse, BaseGridCodeAgent
from grid_code.agents.callbacks import NullCallback, StatusCallback
from grid_code.agents.events import (
    AgentEvent,
    AgentEventType,
    response_complete_event,
    text_delta_event,
    thinking_delta_event,
    thinking_event,
    tool_end_event,
    tool_start_event,
)
from grid_code.agents.mcp_config import get_tool_name
from grid_code.agents.mcp_connection import MCPConnectionConfig, get_mcp_manager
from grid_code.agents.memory import AgentMemory
from grid_code.agents.prompts import (
    get_full_prompt,
    get_optimized_prompt_with_domain,
    get_simple_prompt,
)
from grid_code.agents.result_parser import parse_tool_result
from grid_code.agents.session import SessionManager, SessionState
from grid_code.config import get_settings
from grid_code.mcp.tool_metadata import TOOL_METADATA

# Claude Agent SDK imports
try:
    from claude_agent_sdk import (
        # Message types for isinstance checks
        AssistantMessage,
        ClaudeAgentOptions,
        ClaudeSDKClient,
        # Error types
        ClaudeSDKError,
        CLIConnectionError,
        CLIJSONDecodeError,
        CLINotFoundError,
        HookMatcher,
        ProcessError,
        ResultMessage,
        # Content block types
        TextBlock,
        ThinkingBlock,
        ToolResultBlock,
        ToolUseBlock,
    )
    HAS_CLAUDE_SDK = True
except ImportError:
    HAS_CLAUDE_SDK = False
    # Define placeholder types for type hints when SDK not installed
    AssistantMessage = None  # type: ignore
    ResultMessage = None  # type: ignore
    TextBlock = None  # type: ignore
    ThinkingBlock = None  # type: ignore
    ToolUseBlock = None  # type: ignore
    ToolResultBlock = None  # type: ignore
    ClaudeSDKError = Exception  # type: ignore
    CLINotFoundError = Exception  # type: ignore
    CLIConnectionError = Exception  # type: ignore
    ProcessError = Exception  # type: ignore
    CLIJSONDecodeError = Exception  # type: ignore
    HookMatcher = None  # type: ignore
    logger.warning("claude-agent-sdk not installed. Run: pip install claude-agent-sdk")


class ClaudeAgent(BaseGridCodeAgent):
    """基于 Claude Agent SDK 的 Agent 实现

    使用 Claude Agent SDK 的 ClaudeSDKClient 执行 agent loop，
    通过 MCP Server 连接 GridCode 工具。

    特性:
    - 动态注册全部 MCP 工具（16 个）
    - 支持多会话管理
    - 可选的 Hooks 审计机制
    - 精细化的错误处理

    工具命名规则: mcp__{server_name}__{tool_name}
    例如: mcp__gridcode__get_toc, mcp__gridcode__smart_search
    """

    def __init__(
        self,
        reg_id: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        enable_hooks: bool = True,
        mcp_config: MCPConnectionConfig | None = None,
        status_callback: StatusCallback | None = None,
    ):
        """初始化 Claude Agent

        Args:
            reg_id: 默认规程标识
            model: Claude 模型名称 (haiku, sonnet, opus)
            api_key: Anthropic API Key (通过环境变量 ANTHROPIC_API_KEY 设置)
            enable_hooks: 是否启用 Hooks 审计（默认启用）
            mcp_config: MCP 连接配置（可选，默认从全局配置创建）
            status_callback: 状态回调（可选），用于实时输出 Agent 运行状态
        """
        super().__init__(reg_id)

        if not HAS_CLAUDE_SDK:
            raise ImportError(
                "Claude Agent SDK not installed. "
                "Please run: pip install claude-agent-sdk"
            )

        settings = get_settings()

        # ClaudeAgent 使用 Anthropic 专用配置
        # 模型名称：优先使用传入参数，其次用 ANTHROPIC_MODEL_NAME，留空让 SDK 使用默认值
        self._model = model or settings.anthropic_model_name or ""
        print(f"{settings.anthropic_model_name=}")
        print(f"[ClaudeAgent] Using model: {self._model or '(SDK default)'}")
        self._enable_hooks = enable_hooks

        # 设置环境变量让 Claude SDK 读取
        import os

        # # 使用 Anthropic 专用配置
        # api_key = settings.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")
        # if not api_key:
        #     raise ValueError(
        #         "未配置 Anthropic API Key。"
        #         "请设置环境变量 ANTHROPIC_API_KEY"
        #     )
        # os.environ["ANTHROPIC_API_KEY"] = api_key

        # base_url = settings.anthropic_base_url or os.getenv("ANTHROPIC_BASE_URL", "")
        # if base_url:
        #     # os.environ["ANTHROPIC_BASE_URL"] = base_url
        #     pass

        # 会话管理器
        self._session_manager = SessionManager()

        # 记忆系统（目录缓存 + 相关内容记忆）
        self._enable_memory = settings.enable_agent_memory
        self._memory = AgentMemory() if self._enable_memory else None

        # MCP 连接管理器
        self._mcp_manager = get_mcp_manager(mcp_config)

        # 状态回调
        self._callback = status_callback or NullCallback()

        # 工具调用时间追踪（用于计算耗时）
        self._tool_start_times: dict[str, float] = {}
        self._last_tool_end_time: float | None = None
        self._current_tool_info: dict[str, Any] | None = None

        model_display = self._model or "(SDK default)"
        logger.info(
            f"ClaudeAgent 初始化完成: model={model_display}, "
            f"hooks={self._enable_hooks}, tools={len(TOOL_METADATA)}, "
            f"mcp_transport={self._mcp_manager.config.transport}"
        )

    @property
    def name(self) -> str:
        return "ClaudeAgent"

    @property
    def model(self) -> str:
        return self._model

    def _get_mcp_config(self) -> dict[str, Any]:
        """获取 MCP 服务器配置

        通过统一的 MCPConnectionManager 获取配置。
        支持 stdio 和 SSE 两种传输方式。
        工具将以 mcp__gridcode__<tool_name> 格式暴露。
        """
        return self._mcp_manager.get_claude_sdk_config()

    def _get_allowed_tools(self) -> list[str]:
        """获取允许使用的工具列表

        动态从 TOOL_METADATA 生成，确保与 MCP Server 同步。
        """
        return [get_tool_name(name) for name in TOOL_METADATA.keys()]

    def _build_system_prompt(self) -> str:
        """构建系统提示词

        根据配置选择不同版本的提示词：
        - full: 完整版（向后兼容）
        - optimized: 优化版（默认，减少 token 消耗）
        - simple: 最简版（最快响应）

        同时注入记忆上下文（目录缓存提示 + 已获取的相关内容）
        """
        settings = get_settings()
        include_advanced = getattr(settings, "enable_advanced_tools", False)

        if settings.prompt_mode == "full":
            base_prompt = get_full_prompt(include_advanced)
        elif settings.prompt_mode == "simple":
            base_prompt = get_simple_prompt()
        else:  # optimized
            base_prompt = get_optimized_prompt_with_domain(include_advanced)

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

    def _build_hooks(self) -> dict[str, list[HookMatcher]] | None:
        """构建 Hooks 配置

        返回 PreToolUse 和 PostToolUse 的钩子列表。
        根据配置决定是否启用 OTel 追踪。
        """
        if not self._enable_hooks or HookMatcher is None:
            return None

        settings = get_settings()

        # 检查是否启用 OTel 追踪
        enable_otel = settings.timing_backend == "otel"

        # 使用组合 hooks 工厂函数
        from grid_code.agents.otel_hooks import get_combined_hooks

        combined = get_combined_hooks(
            enable_audit=True,  # 始终启用审计 hooks
            enable_otel=enable_otel,
            otel_service_name=settings.otel_service_name,
            otel_exporter_type=settings.otel_exporter_type,
            otel_endpoint=settings.otel_endpoint,
        )

        # 转换为 HookMatcher 格式
        result = {}
        if combined.get("PreToolUse"):
            result["PreToolUse"] = [HookMatcher(hooks=combined["PreToolUse"])]
        if combined.get("PostToolUse"):
            result["PostToolUse"] = [HookMatcher(hooks=combined["PostToolUse"])]

        return result if result else None

    def _build_options(self) -> ClaudeAgentOptions:
        """构建 Agent 选项"""
        # 禁用内置的 computer use 工具，强制使用 MCP 工具
        disallowed = [
            "Bash", "Read", "Write", "Edit", "Glob", "Grep",
            "LS", "MultiEdit", "NotebookEdit", "NotebookRead",
            "TodoRead", "TodoWrite", "WebFetch", "WebSearch",
        ]

        options_kwargs = {
            "system_prompt": self._build_system_prompt(),
            "mcp_servers": self._get_mcp_config(),
            "allowed_tools": self._get_allowed_tools(),
            "disallowed_tools": disallowed,
            "max_turns": 20,  # 允许多轮工具调用
            "permission_mode": "bypassPermissions",  # 自动执行工具
            "include_partial_messages": True,  # 启用流式事件
        }

        # 只有当指定了模型时才传递，否则让 SDK 使用默认值
        if self._model:
            options_kwargs["model"] = self._model

        # 添加 Hooks（如果启用）
        hooks = self._build_hooks()
        if hooks:
            options_kwargs["hooks"] = hooks

        return ClaudeAgentOptions(**options_kwargs)

    async def chat(
        self,
        message: str,
        session_id: str | None = None,
    ) -> AgentResponse:
        """与 Agent 对话

        使用 ClaudeSDKClient 作为上下文管理器，确保连接正确清理。

        Args:
            message: 用户消息
            session_id: 会话 ID（可选，用于多会话隔离）

        Returns:
            AgentResponse
        """
        # 获取或创建会话
        session = self._session_manager.get_or_create(session_id)
        session.reset_per_query()

        # 重置工具追踪状态
        self._tool_start_times = {}
        self._last_tool_end_time = None
        self._current_tool_info = None

        # 流式内容追踪（避免重复发送）
        self._stream_thinking_sent = False
        self._stream_text_sent = False

        final_result = ""

        # 记录开始时间
        start_time = time.time()

        # 发送思考开始事件
        await self._callback.on_event(thinking_event(start=True))

        # 设置 Hooks 的状态回调（让 hooks 能够发送详细的工具结果事件）
        from grid_code.agents.hooks import set_status_callback
        set_status_callback(self._callback)

        try:
            # 使用上下文管理器确保连接正确清理
            async with ClaudeSDKClient(options=self._build_options()) as client:
                # 发送查询
                await client.query(message, session_id=session.session_id)

                # 接收响应
                async for event in client.receive_response():
                    await self._process_event(event, session)

                    # 检查最终结果 (ResultMessage)
                    if ResultMessage is not None and isinstance(event, ResultMessage):
                        if event.result:
                            final_result = event.result
                        elif session.tool_calls:
                            final_result = session.tool_calls[-1].get("output", "")
                        break

                # 如果没有通过 ResultMessage 获取，尝试从最后的消息中提取
                if not final_result:
                    final_result = self._get_assembled_text(session)

        except CLINotFoundError:
            logger.error("Claude Code CLI 未安装")
            await self._callback.on_event(thinking_event(start=False))
            return AgentResponse(
                content="错误：Claude Code CLI 未安装。请确保 claude-agent-sdk 已正确安装。",
                sources=[],
                tool_calls=session.tool_calls,
            )

        except CLIConnectionError as e:
            logger.error(f"连接 Claude Code 失败: {e}")
            await self._callback.on_event(thinking_event(start=False))
            return AgentResponse(
                content=f"连接失败：{str(e)}。请检查网络连接和 API Key 配置。",
                sources=[],
                tool_calls=session.tool_calls,
            )

        except ProcessError as e:
            exit_code = getattr(e, "exit_code", -1)
            stderr = getattr(e, "stderr", str(e))
            logger.error(f"进程错误 (exit_code={exit_code}): {stderr}")
            await self._callback.on_event(thinking_event(start=False))
            return AgentResponse(
                content=f"执行失败 (代码 {exit_code}): {stderr or '未知错误'}",
                sources=list(set(session.sources)),
                tool_calls=session.tool_calls,
            )

        except CLIJSONDecodeError as e:
            line = getattr(e, "line", str(e))
            logger.error(f"JSON 解析失败: {line}")
            await self._callback.on_event(thinking_event(start=False))
            return AgentResponse(
                content="响应解析失败：服务返回了无效的 JSON 数据。",
                sources=[],
                tool_calls=session.tool_calls,
            )

        except ClaudeSDKError as e:
            logger.error(f"Claude SDK 错误: {e}")
            await self._callback.on_event(thinking_event(start=False))
            return AgentResponse(
                content=f"SDK 错误: {str(e)}",
                sources=list(set(session.sources)),
                tool_calls=session.tool_calls,
            )

        except Exception as e:
            logger.exception(f"未知错误: {e}")
            await self._callback.on_event(thinking_event(start=False))
            return AgentResponse(
                content=f"查询失败: {str(e)}",
                sources=list(set(session.sources)),
                tool_calls=session.tool_calls,
            )

        # 发送思考结束事件
        await self._callback.on_event(thinking_event(start=False))

        # 清理 Hooks 的状态回调
        set_status_callback(None)

        # 计算总耗时
        duration_ms = (time.time() - start_time) * 1000

        # 发送响应完成事件
        await self._callback.on_event(
            response_complete_event(
                total_tool_calls=len(session.tool_calls),
                total_sources=len(set(session.sources)),
                duration_ms=duration_ms,
            )
        )

        return AgentResponse(
            content=final_result,
            sources=list(set(session.sources)),  # 去重
            tool_calls=session.tool_calls,
        )

    async def _process_event(self, event: Any, session: SessionState) -> None:
        """处理 SDK 事件

        使用 isinstance() 检查事件类型，符合 SDK 最佳实践。
        同时更新记忆系统并发送事件到回调。

        支持的事件类型：
        - StreamEvent: 流式事件，包含 content_block_delta 等
        - AssistantMessage: 包含 TextBlock, ThinkingBlock, ToolUseBlock
        - ToolResultBlock / tool_result: 工具执行结果
        """
        import json

        # 处理 StreamEvent（流式事件，用于实时输出）
        if hasattr(event, 'event') and isinstance(getattr(event, 'event', None), dict):
            inner_event = event.event
            event_type = inner_event.get('type', '')

            if event_type == 'content_block_delta':
                delta = inner_event.get('delta', {})
                delta_type = delta.get('type', '')

                # 思考内容增量
                if delta_type == 'thinking_delta' and 'thinking' in delta:
                    thinking_text = delta['thinking']
                    # DEBUG: 记录思考增量，帮助调试中间推理是否被捕获
                    preview = thinking_text[:80].replace('\n', ' ') if thinking_text else ''
                    logger.debug(f"[Thinking Delta] {len(thinking_text)} chars: {preview}...")
                    await self._callback.on_event(thinking_delta_event(thinking_text))
                    self._stream_thinking_sent = True

                # 文本内容增量
                elif delta_type == 'text_delta' and 'text' in delta:
                    await self._callback.on_event(text_delta_event(delta['text']))
                    self._stream_text_sent = True

                # 工具输入增量（用于更新工具参数）
                elif delta_type == 'input_json_delta' and 'partial_json' in delta:
                    # 累积工具输入（后续可能需要）
                    pass

            # 内容块开始（可用于发送开始事件）
            elif event_type == 'content_block_start':
                content_block = inner_event.get('content_block', {})
                block_type = content_block.get('type', '')
                block_index = inner_event.get('index', 0)

                if block_type == 'thinking':
                    # 思考开始，重置标志
                    logger.debug(f"[Thinking Block Start] index={block_index}")
                    self._stream_thinking_sent = False
                elif block_type == 'text':
                    # 文本开始，重置标志
                    self._stream_text_sent = False
                elif block_type == 'tool_use':
                    # 工具调用开始
                    tool_name = content_block.get('name', '')
                    tool_id = content_block.get('id', '')
                    if tool_name:
                        now = time.time()
                        # 计算思考耗时
                        thinking_duration_ms = None
                        if self._last_tool_end_time is not None:
                            thinking_duration_ms = (now - self._last_tool_end_time) * 1000
                        self._tool_start_times[tool_id] = now

                        # 记录当前工具信息（用于追踪，hooks 会发送事件）
                        self._current_tool_info = {
                            "tool_id": tool_id,
                            "tool_name": tool_name,
                            "block_index": block_index,
                            "thinking_duration_ms": thinking_duration_ms,
                        }

                        # 初始记录工具调用（hooks 的 pre_tool_audit_hook 会发送 tool_start_event）
                        session.add_tool_call(name=tool_name, input_data={})
                        if session.tool_calls:
                            session.tool_calls[-1]["tool_id"] = tool_id
                            session.tool_calls[-1]["thinking_duration_ms"] = thinking_duration_ms

                        # 注意：tool_start_event 由 hooks.pre_tool_audit_hook 发送，此处不重复发送
                        logger.debug(f"Tool call start (stream): {tool_name}, id={tool_id}")

            # 内容块结束
            # 注意：tool_end_event 由 hooks.post_tool_audit_hook 发送（带有详细结果），此处不重复发送
            elif event_type == 'content_block_stop':
                # 清除当前工具信息（工具调用的完整生命周期由 hooks 管理）
                if self._current_tool_info:
                    logger.debug(f"Tool call block complete (stream): {self._current_tool_info.get('tool_name', 'unknown')}")
                    self._current_tool_info = None

            return  # StreamEvent 处理完毕，不继续后续处理

        # 处理 AssistantMessage
        if AssistantMessage is not None and isinstance(event, AssistantMessage):
            for block in event.content:
                # TextBlock - 文本内容（跳过已通过流式发送的）
                if TextBlock is not None and isinstance(block, TextBlock):
                    if block.text and not self._stream_text_sent:
                        await self._callback.on_event(text_delta_event(block.text))

                # ThinkingBlock - 思考内容（跳过已通过流式发送的）
                elif ThinkingBlock is not None and isinstance(block, ThinkingBlock):
                    thinking_text = getattr(block, "thinking", None)
                    if thinking_text and not self._stream_thinking_sent:
                        await self._callback.on_event(thinking_delta_event(thinking_text))

                # ToolUseBlock - 工具调用开始（完整信息）
                elif ToolUseBlock is not None and isinstance(block, ToolUseBlock):
                    tool_name = block.name
                    tool_input = block.input if isinstance(block.input, dict) else {}
                    tool_id = getattr(block, "id", "") or ""

                    # 检查是否已经从 content_block_start 记录过
                    existing_call = None
                    for tc in reversed(session.tool_calls):
                        if tc.get("tool_id") == tool_id:
                            existing_call = tc
                            break

                    if existing_call:
                        # 更新已有记录的输入（从 content_block_start 创建的）
                        existing_call["input"] = tool_input
                        logger.debug(f"Tool call updated: {tool_name}, id={tool_id}")
                    else:
                        # 未从 stream 事件创建，正常记录
                        now = time.time()

                        # 计算思考耗时
                        thinking_duration_ms = None
                        if self._last_tool_end_time is not None:
                            thinking_duration_ms = (now - self._last_tool_end_time) * 1000

                        # 记录开始时间
                        self._tool_start_times[tool_id] = now

                        # 记录到会话
                        session.add_tool_call(name=tool_name, input_data=tool_input)
                        if session.tool_calls:
                            session.tool_calls[-1]["tool_id"] = tool_id
                            session.tool_calls[-1]["thinking_duration_ms"] = thinking_duration_ms

                        # 当 hooks 启用时，pre_tool_audit_hook 会发送 tool_start_event
                        # 此处不重复发送
                        if not self._enable_hooks:
                            await self._callback.on_event(
                                tool_start_event(tool_name, tool_input, tool_id)
                            )

                        logger.debug(f"Tool call start: {tool_name}, id={tool_id}")

                # ToolResultBlock - 工具返回结果
                elif ToolResultBlock is not None and isinstance(block, ToolResultBlock):
                    await self._handle_tool_result(block, session)

        # 处理独立的 ToolResultBlock（某些 SDK 版本可能直接返回）
        if ToolResultBlock is not None and isinstance(event, ToolResultBlock):
            await self._handle_tool_result(event, session)

        # 从工具结果中提取来源并更新记忆（兼容旧格式）
        if hasattr(event, "type") and getattr(event, "type", None) == "tool_result":
            content = getattr(event, "content", None)
            tool_name = getattr(event, "tool_name", None)
            tool_use_id = getattr(event, "tool_use_id", "")
            if content:
                self._extract_sources(content, session)
                # 更新记忆系统
                if tool_name:
                    self._update_memory(tool_name, content)
                # 发送工具结束事件
                await self._emit_tool_end_event(tool_name or "unknown", tool_use_id, content, session)

        # 处理 content 属性（可能包含工具结果）
        if hasattr(event, "content"):
            content = getattr(event, "content", None)
            if content and not isinstance(event, AssistantMessage):
                self._extract_sources(content, session)

    async def _handle_tool_result(self, block: Any, session: SessionState) -> None:
        """处理工具结果块

        Args:
            block: ToolResultBlock 实例
            session: 会话状态
        """
        tool_use_id = getattr(block, "tool_use_id", "") or ""
        content = getattr(block, "content", None)

        # 查找对应的工具调用
        tool_name = "unknown"
        tool_input = {}
        thinking_duration_ms = None

        for tc in reversed(session.tool_calls):
            if tc.get("tool_id") == tool_use_id:
                tool_name = tc.get("name", "unknown")
                tool_input = tc.get("input", {})
                thinking_duration_ms = tc.get("thinking_duration_ms")
                tc["output"] = content
                break

        # 提取来源
        self._extract_sources(content, session)

        # 更新记忆
        self._update_memory(tool_name, content)

        # 发送工具结束事件
        await self._emit_tool_end_event(tool_name, tool_use_id, content, session, thinking_duration_ms)

    async def _emit_tool_end_event(
        self,
        tool_name: str,
        tool_id: str,
        result: Any,
        session: SessionState,
        thinking_duration_ms: float | None = None,
    ) -> None:
        """发送工具调用结束事件

        注意：当 hooks 启用时，post_tool_audit_hook 会发送带详细结果的事件，
        此方法仅用于更新内部状态。事件发送由 hooks 统一处理。

        Args:
            tool_name: 工具名称
            tool_id: 工具调用 ID
            result: 工具返回结果
            session: 会话状态
            thinking_duration_ms: 思考耗时（可选）
        """
        now = time.time()

        # 计算执行耗时
        start_time = self._tool_start_times.pop(tool_id, None)
        if start_time is not None:
            duration_ms = (now - start_time) * 1000
        else:
            duration_ms = 0

        # 记录工具结束时间
        self._last_tool_end_time = now

        # 如果 hooks 启用，事件由 post_tool_audit_hook 发送（带有详细结果）
        # 此处不重复发送，仅记录日志
        if self._enable_hooks:
            logger.debug(f"Tool call end (via hooks): {tool_name}, duration={duration_ms:.1f}ms")
            return

        # 当 hooks 未启用时，此处发送事件
        # 使用结果解析器提取详细摘要
        summary = parse_tool_result(tool_name, result)

        # 获取工具输入（从 session 中查找）
        tool_input = {}
        for tc in reversed(session.tool_calls):
            if tc.get("tool_id") == tool_id or tc.get("name") == tool_name:
                tool_input = tc.get("input", {})
                if thinking_duration_ms is None:
                    thinking_duration_ms = tc.get("thinking_duration_ms")
                break

        # 发送工具调用完成事件
        await self._callback.on_event(
            tool_end_event(
                tool_name=tool_name,
                tool_id=tool_id,
                duration_ms=duration_ms,
                result_count=summary.result_count,
                tool_input=tool_input,
                result_type=summary.result_type,
                chapter_count=summary.chapter_count,
                page_sources=summary.page_sources,
                content_preview=summary.content_preview,
                thinking_duration_ms=thinking_duration_ms,
            )
        )

        logger.debug(f"Tool call end: {tool_name}, duration={duration_ms:.1f}ms")

    def _update_memory(self, tool_name: str, result: Any) -> None:
        """根据工具结果更新记忆系统

        Args:
            tool_name: 工具名称（如 mcp__gridcode__get_toc）
            result: 工具返回结果
        """
        # 记忆系统未启用时跳过
        if not self._memory:
            return

        import json

        # 解析 JSON 字符串
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return

        if not isinstance(result, dict):
            return

        # 提取真实工具名（去除 mcp__gridcode__ 前缀）
        simple_name = tool_name
        if "__" in tool_name:
            parts = tool_name.split("__")
            simple_name = parts[-1] if len(parts) > 1 else tool_name

        # 根据工具类型更新记忆
        if simple_name == "get_toc":
            # 缓存目录
            reg_id = result.get("reg_id") or self.reg_id
            if reg_id:
                self._memory.cache_toc(reg_id, result)
                logger.debug(f"[Memory] 缓存目录: {reg_id}")

        elif simple_name == "smart_search":
            # 提取搜索结果
            results = result.get("results", [])
            if results:
                self._memory.add_search_results(results)
                logger.debug(f"[Memory] 添加搜索结果: {len(results)} 条")

        elif simple_name == "read_page_range":
            # 记录页面内容
            content = result.get("content_markdown", "")
            source = result.get("source", "")
            if content and source:
                self._memory.add_page_content(content, source)
                logger.debug(f"[Memory] 添加页面内容: {source}")

    def _extract_sources(self, result: Any, session: SessionState) -> None:
        """从工具结果中提取来源信息

        支持多种结果格式：
        - dict: 检查 source 字段
        - list: 递归处理每个元素
        - str: 尝试解析为 JSON
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

    def _get_assembled_text(self, session: SessionState) -> str:
        """从工具调用结果中组装最终文本

        如果没有明确的 ResultMessage，尝试从最后的工具输出中提取。
        """
        if not session.tool_calls:
            return ""

        # 查找最后一个有输出的工具调用
        for tool_call in reversed(session.tool_calls):
            output = tool_call.get("output")
            if output:
                if isinstance(output, dict):
                    # 尝试获取 content_markdown 或 content
                    return output.get("content_markdown", output.get("content", str(output)))
                elif isinstance(output, str):
                    return output

        return ""

    async def reset(self, session_id: str | None = None):
        """重置对话历史

        Args:
            session_id: 要重置的会话 ID，如果为 None 则重置默认会话
        """
        self._session_manager.reset(session_id)
        if self._memory:
            self._memory.clear_query_context()  # 清除查询上下文，保留目录缓存
        logger.debug(f"Session reset: {session_id or 'default'}")

    async def reset_all(self):
        """重置所有会话"""
        self._session_manager.reset_all()
        if self._memory:
            self._memory.reset()  # 完全重置记忆（包括目录缓存）
        logger.debug("All sessions reset")

    def get_sessions(self) -> list[str]:
        """获取所有活跃会话 ID"""
        return self._session_manager.get_all_sessions()

    def get_session_info(self, session_id: str | None = None) -> dict | None:
        """获取会话信息"""
        return self._session_manager.get_session_info(session_id)
