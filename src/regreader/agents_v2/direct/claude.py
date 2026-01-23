"""Claude Agent 实现

基于 agentex 框架的 Claude Agent，使用 Claude Agent SDK。
"""

from __future__ import annotations

import time
from typing import Any, AsyncGenerator

from loguru import logger

from ...agentex.agent import BaseAgent
from ...agentex.config import ClaudeConfig
from ...agentex.types import AgentResponse as AgentexResponse, Context
from ...agents.prompts import (
    get_full_prompt,
    get_optimized_prompt_with_domain,
    get_simple_prompt,
)
from ...agents.shared.callbacks import StatusCallback
from ...agents.shared.mcp_config import get_tool_name
from ...agents.shared.mcp_connection import MCPConnectionConfig, get_mcp_manager
from ...core.config import get_settings
from ...mcp.tool_metadata import TOOL_METADATA
from ...storage import PageStore
from ..base import AgentResponse, RegReaderAgent
from ..config import ClaudeAgentConfig, RegReaderConfig
from ..events import EventAdapter

# Claude Agent SDK imports
try:
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ClaudeSDKClient,
        ClaudeSDKError,
        CLIConnectionError,
        CLIJSONDecodeError,
        CLINotFoundError,
        HookMatcher,
        ProcessError,
        ResultMessage,
        TextBlock,
        ThinkingBlock,
        ToolResultBlock,
        ToolUseBlock,
    )

    HAS_CLAUDE_SDK = True
except ImportError:
    HAS_CLAUDE_SDK = False
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
    ClaudeAgentOptions = None  # type: ignore
    ClaudeSDKClient = None  # type: ignore


class ClaudeAgent(RegReaderAgent):
    """基于 Claude Agent SDK 的 Agent 实现

    使用 Claude Agent SDK 的 ClaudeSDKClient 执行 agent loop，
    通过 MCP Server 连接 RegReader 工具。

    特性:
    - 动态注册全部 MCP 工具
    - 支持多会话管理
    - 可选的 Hooks 审计机制
    - 精细化的错误处理

    工具命名规则: mcp__{server_name}__{tool_name}
    例如: mcp__gridcode__get_toc, mcp__gridcode__smart_search
    """

    def __init__(
        self,
        config: ClaudeAgentConfig | RegReaderConfig | None = None,
        reg_id: str | None = None,
        model: str | None = None,
        enable_hooks: bool = True,
        mcp_config: MCPConnectionConfig | None = None,
        status_callback: StatusCallback | None = None,
    ):
        """初始化 Claude Agent

        Args:
            config: Agent 配置（可选）
            reg_id: 默认规程标识
            model: Claude 模型名称
            enable_hooks: 是否启用 Hooks 审计
            mcp_config: MCP 连接配置
            status_callback: 状态回调
        """
        if not HAS_CLAUDE_SDK:
            raise ImportError(
                "Claude Agent SDK not installed. "
                "Please run: pip install claude-agent-sdk"
            )

        # 构建配置
        if config is None:
            config = ClaudeAgentConfig()

        # 如果传入的是 RegReaderConfig，转换为 ClaudeAgentConfig
        if not isinstance(config, ClaudeAgentConfig):
            config = ClaudeAgentConfig(
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

        # 模型名称
        self._model = model or config.model or settings.anthropic_model_name or ""
        self._enable_hooks = enable_hooks if isinstance(config, ClaudeAgentConfig) else config.enable_hooks if hasattr(config, 'enable_hooks') else True

        # MCP 连接管理器
        self._mcp_manager = get_mcp_manager(config.mcp_config)

        # PageStore 实例（用于获取规程列表）
        self._page_store = PageStore(settings.pages_dir)
        self._regulations_cache: list[dict] | None = None

        # 工具调用追踪
        self._tool_start_times: dict[str, float] = {}
        self._last_tool_end_time: float | None = None
        self._current_tool_info: dict[str, Any] | None = None

        logger.info(
            f"ClaudeAgent (v2) 初始化完成: model={self._model or '(SDK default)'}, "
            f"hooks={self._enable_hooks}, tools={len(TOOL_METADATA)}"
        )

    @property
    def name(self) -> str:
        """Agent 名称"""
        return "ClaudeAgent"

    @property
    def model(self) -> str:
        """使用的模型名称"""
        return self._model

    async def _create_agent(self) -> BaseAgent:
        """创建底层 agentex Agent

        注意：ClaudeAgent 直接使用 Claude SDK，不通过 agentex 框架。
        此方法返回 None，chat() 方法直接使用 ClaudeSDKClient。
        """
        # ClaudeAgent 不使用 agentex 的 BaseAgent
        # 而是直接使用 Claude Agent SDK
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

    def _get_mcp_config(self) -> dict[str, Any]:
        """获取 MCP 服务器配置"""
        return self._mcp_manager.get_claude_sdk_config()

    def _get_allowed_tools(self) -> list[str]:
        """获取允许使用的工具列表"""
        return [get_tool_name(name) for name in TOOL_METADATA.keys()]

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        settings = get_settings()
        include_advanced = getattr(settings, "enable_advanced_tools", False)
        regulations = self._get_regulations()

        if self._config.prompt_mode == "full":
            base_prompt = get_full_prompt(include_advanced, regulations)
        elif self._config.prompt_mode == "simple":
            base_prompt = get_simple_prompt()
        else:  # optimized
            base_prompt = get_optimized_prompt_with_domain(include_advanced, regulations)

        if self.reg_id:
            base_prompt += f"\n\n# 当前规程\n默认规程: {self.reg_id}"

        # 注入记忆上下文
        if self._memory:
            toc_hint = self._memory.get_toc_cache_hint()
            if toc_hint:
                base_prompt += toc_hint

            memory_context = self._memory.get_memory_context()
            if memory_context:
                base_prompt += f"\n\n{memory_context}"

        return base_prompt

    def _build_hooks(self) -> dict[str, list] | None:
        """构建 Hooks 配置"""
        if not self._enable_hooks or HookMatcher is None:
            return None

        settings = get_settings()
        enable_otel = settings.timing_backend == "otel"

        from ...agents.shared.otel_hooks import get_combined_hooks

        combined = get_combined_hooks(
            enable_audit=True,
            enable_otel=enable_otel,
            otel_service_name=settings.otel_service_name,
            otel_exporter_type=settings.otel_exporter_type,
            otel_endpoint=settings.otel_endpoint,
        )

        result = {}
        if combined.get("PreToolUse"):
            result["PreToolUse"] = [HookMatcher(hooks=combined["PreToolUse"])]
        if combined.get("PostToolUse"):
            result["PostToolUse"] = [HookMatcher(hooks=combined["PostToolUse"])]

        return result if result else None

    def _build_options(self) -> "ClaudeAgentOptions":
        """构建 Agent 选项"""
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
            "max_turns": self._config.max_iterations * 2,
            "permission_mode": "bypassPermissions",
            "include_partial_messages": True,
        }

        if self._model:
            options_kwargs["model"] = self._model

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

        Args:
            message: 用户消息
            session_id: 会话 ID

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

        final_result = ""
        start_time = time.time()

        # 发送思考开始事件
        await self._callback.on_event(EventAdapter.create_thinking_event(start=True))

        # 设置 Hooks 的状态回调
        from ...agents.hooks import set_status_callback
        set_status_callback(self._callback)

        try:
            async with ClaudeSDKClient(options=self._build_options()) as client:
                await client.query(message, session_id=session.session_id)

                async for event in client.receive_response():
                    await self._process_event(event, session)

                    if ResultMessage is not None and isinstance(event, ResultMessage):
                        if event.result:
                            final_result = event.result
                        elif session.tool_calls:
                            final_result = session.tool_calls[-1].get("output", "")
                        break

                if not final_result:
                    final_result = self._get_assembled_text(session)

        except CLINotFoundError:
            logger.error("Claude Code CLI 未安装")
            await self._callback.on_event(EventAdapter.create_thinking_event(start=False))
            return AgentResponse(
                content="错误：Claude Code CLI 未安装。",
                sources=[],
                tool_calls=session.tool_calls,
            )

        except CLIConnectionError as e:
            logger.error(f"连接 Claude Code 失败: {e}")
            await self._callback.on_event(EventAdapter.create_thinking_event(start=False))
            return AgentResponse(
                content=f"连接失败：{str(e)}",
                sources=[],
                tool_calls=session.tool_calls,
            )

        except ProcessError as e:
            exit_code = getattr(e, "exit_code", -1)
            stderr = getattr(e, "stderr", str(e))
            logger.error(f"进程错误 (exit_code={exit_code}): {stderr}")
            await self._callback.on_event(EventAdapter.create_thinking_event(start=False))
            return AgentResponse(
                content=f"执行失败 (代码 {exit_code}): {stderr or '未知错误'}",
                sources=list(set(session.sources)),
                tool_calls=session.tool_calls,
            )

        except Exception as e:
            logger.exception(f"未知错误: {e}")
            await self._callback.on_event(EventAdapter.create_thinking_event(start=False))
            return AgentResponse(
                content=f"查询失败: {str(e)}",
                sources=list(set(session.sources)),
                tool_calls=session.tool_calls,
            )

        # 发送思考结束事件
        await self._callback.on_event(EventAdapter.create_thinking_event(start=False))

        # 清理 Hooks 的状态回调
        set_status_callback(None)

        # 计算总耗时
        duration_ms = (time.time() - start_time) * 1000

        # 发送响应完成事件
        await self._callback.on_event(
            EventAdapter.create_response_complete_event(
                content=final_result,
                sources=list(set(session.sources)),
            )
        )

        return AgentResponse(
            content=final_result,
            sources=list(set(session.sources)),
            tool_calls=session.tool_calls,
        )

    async def _process_event(self, event: Any, session) -> None:
        """处理 SDK 事件"""
        # 处理 StreamEvent
        if hasattr(event, 'event') and isinstance(getattr(event, 'event', None), dict):
            inner_event = event.event
            event_type = inner_event.get('type', '')

            if event_type == 'content_block_delta':
                delta = inner_event.get('delta', {})
                delta_type = delta.get('type', '')

                if delta_type == 'thinking_delta' and 'thinking' in delta:
                    pass  # 思考内容增量

                elif delta_type == 'text_delta' and 'text' in delta:
                    pass  # 文本内容增量

            elif event_type == 'content_block_start':
                content_block = inner_event.get('content_block', {})
                block_type = content_block.get('type', '')

                if block_type == 'tool_use':
                    tool_name = content_block.get('name', '')
                    tool_id = content_block.get('id', '')
                    if tool_name:
                        now = time.time()
                        self._tool_start_times[tool_id] = now
                        session.add_tool_call(name=tool_name, input_data={})
                        if session.tool_calls:
                            session.tool_calls[-1]["tool_id"] = tool_id

            return

        # 处理 AssistantMessage
        if AssistantMessage is not None and isinstance(event, AssistantMessage):
            for block in event.content:
                if ToolUseBlock is not None and isinstance(block, ToolUseBlock):
                    tool_name = block.name
                    tool_input = block.input if isinstance(block.input, dict) else {}
                    tool_id = getattr(block, "id", "") or ""

                    existing_call = None
                    for tc in reversed(session.tool_calls):
                        if tc.get("tool_id") == tool_id:
                            existing_call = tc
                            break

                    if existing_call:
                        existing_call["input"] = tool_input
                    else:
                        now = time.time()
                        self._tool_start_times[tool_id] = now
                        session.add_tool_call(name=tool_name, input_data=tool_input)
                        if session.tool_calls:
                            session.tool_calls[-1]["tool_id"] = tool_id

                elif ToolResultBlock is not None and isinstance(block, ToolResultBlock):
                    await self._handle_tool_result(block, session)

        # 处理独立的 ToolResultBlock
        if ToolResultBlock is not None and isinstance(event, ToolResultBlock):
            await self._handle_tool_result(event, session)

    async def _handle_tool_result(self, block: Any, session) -> None:
        """处理工具结果块"""
        tool_use_id = getattr(block, "tool_use_id", "") or ""
        content = getattr(block, "content", None)

        tool_name = "unknown"
        for tc in reversed(session.tool_calls):
            if tc.get("tool_id") == tool_use_id:
                tool_name = tc.get("name", "unknown")
                tc["output"] = content
                break

        # 提取来源
        self._extract_sources(content, session)

        # 更新记忆
        self._update_memory(tool_name, content)

    def _update_memory(self, tool_name: str, result: Any) -> None:
        """根据工具结果更新记忆系统"""
        if not self._memory:
            return

        import json

        if isinstance(result, str):
            try:
                result = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return

        if not isinstance(result, dict):
            return

        simple_name = tool_name
        if "__" in tool_name:
            parts = tool_name.split("__")
            simple_name = parts[-1] if len(parts) > 1 else tool_name

        if simple_name == "get_toc":
            reg_id = result.get("reg_id") or self.reg_id
            if reg_id:
                self._memory.cache_toc(reg_id, result)

        elif simple_name == "smart_search":
            results = result.get("results", [])
            if results:
                self._memory.add_search_results(results, self.reg_id)

    def _get_assembled_text(self, session) -> str:
        """从工具调用结果中组装最终文本"""
        if not session.tool_calls:
            return ""

        for tool_call in reversed(session.tool_calls):
            output = tool_call.get("output")
            if output:
                if isinstance(output, dict):
                    return output.get("content_markdown", output.get("content", str(output)))
                elif isinstance(output, str):
                    return output

        return ""

    async def reset(self, session_id: str | None = None) -> None:
        """重置对话历史"""
        self._session_manager.reset(session_id)
        if self._memory:
            self._memory.clear_query_context()

    async def close(self) -> None:
        """释放资源"""
        pass  # ClaudeSDKClient 使用上下文管理器，无需手动关闭
