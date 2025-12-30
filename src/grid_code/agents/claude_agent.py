"""Claude Agent SDK 实现

使用 Claude Agent SDK 实现 GridCode Agent。
https://github.com/anthropics/claude-agent-sdk-python
"""

from typing import Any

from loguru import logger

from grid_code.agents.base import AgentResponse, BaseGridCodeAgent
from grid_code.agents.mcp_config import MCP_SERVER_ARGS, get_mcp_command, get_mcp_stdio_config, get_tool_name
from grid_code.agents.prompts import SYSTEM_PROMPT
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
        ToolUseBlock,
    )
    HAS_CLAUDE_SDK = True
except ImportError:
    HAS_CLAUDE_SDK = False
    # Define placeholder types for type hints when SDK not installed
    AssistantMessage = None  # type: ignore
    ResultMessage = None  # type: ignore
    TextBlock = None  # type: ignore
    ToolUseBlock = None  # type: ignore
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
    ):
        """初始化 Claude Agent

        Args:
            reg_id: 默认规程标识
            model: Claude 模型名称 (haiku, sonnet, opus)
            api_key: Anthropic API Key (通过环境变量 ANTHROPIC_API_KEY 设置)
            enable_hooks: 是否启用 Hooks 审计（默认启用）
        """
        super().__init__(reg_id)

        if not HAS_CLAUDE_SDK:
            raise ImportError(
                "Claude Agent SDK not installed. "
                "Please run: pip install claude-agent-sdk"
            )

        settings = get_settings()
        self._model = model or settings.default_model
        self._enable_hooks = enable_hooks

        # SDK 使用环境变量 ANTHROPIC_API_KEY，此处仅验证
        api_key = api_key or settings.anthropic_api_key
        if not api_key:
            raise ValueError(
                "未配置 Anthropic API Key。"
                "请设置环境变量 ANTHROPIC_API_KEY"
            )

        # 会话管理器
        self._session_manager = SessionManager()

        logger.info(
            f"ClaudeAgent 初始化完成: model={self._model}, "
            f"hooks={self._enable_hooks}, tools={len(TOOL_METADATA)}"
        )

    @property
    def name(self) -> str:
        return "ClaudeAgent"

    @property
    def model(self) -> str:
        return self._model

    def _get_mcp_config(self) -> dict[str, Any]:
        """获取 MCP 服务器配置

        GridCode MCP Server 通过 stdio 模式运行。
        工具将以 mcp__gridcode__<tool_name> 格式暴露。
        """
        return get_mcp_stdio_config()

    def _get_allowed_tools(self) -> list[str]:
        """获取允许使用的工具列表

        动态从 TOOL_METADATA 生成，确保与 MCP Server 同步。
        """
        return [get_tool_name(name) for name in TOOL_METADATA.keys()]

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

    def _build_hooks(self) -> dict[str, list[HookMatcher]] | None:
        """构建 Hooks 配置

        返回 PreToolUse 和 PostToolUse 的钩子列表。
        """
        if not self._enable_hooks or HookMatcher is None:
            return None

        # 延迟导入避免循环依赖
        from grid_code.agents.hooks import (
            post_tool_audit_hook,
            pre_tool_audit_hook,
            source_extraction_hook,
        )

        return {
            "PreToolUse": [
                HookMatcher(hooks=[pre_tool_audit_hook]),
            ],
            "PostToolUse": [
                HookMatcher(hooks=[post_tool_audit_hook, source_extraction_hook]),
            ],
        }

    def _build_options(self) -> ClaudeAgentOptions:
        """构建 Agent 选项"""
        options_kwargs = {
            "system_prompt": self._build_system_prompt(),
            "mcp_servers": self._get_mcp_config(),
            "allowed_tools": self._get_allowed_tools(),
            "model": self._model,
            "max_turns": 20,  # 允许多轮工具调用
            "permission_mode": "bypassPermissions",  # 自动执行工具
        }

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

        final_result = ""

        try:
            # 使用上下文管理器确保连接正确清理
            async with ClaudeSDKClient(options=self._build_options()) as client:
                # 发送查询
                await client.query(message, session_id=session.session_id)

                # 接收响应
                async for event in client.receive_response():
                    self._process_event(event, session)

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
            return AgentResponse(
                content="错误：Claude Code CLI 未安装。请确保 claude-agent-sdk 已正确安装。",
                sources=[],
                tool_calls=session.tool_calls,
            )

        except CLIConnectionError as e:
            logger.error(f"连接 Claude Code 失败: {e}")
            return AgentResponse(
                content=f"连接失败：{str(e)}。请检查网络连接和 API Key 配置。",
                sources=[],
                tool_calls=session.tool_calls,
            )

        except ProcessError as e:
            exit_code = getattr(e, "exit_code", -1)
            stderr = getattr(e, "stderr", str(e))
            logger.error(f"进程错误 (exit_code={exit_code}): {stderr}")
            return AgentResponse(
                content=f"执行失败 (代码 {exit_code}): {stderr or '未知错误'}",
                sources=list(set(session.sources)),
                tool_calls=session.tool_calls,
            )

        except CLIJSONDecodeError as e:
            line = getattr(e, "line", str(e))
            logger.error(f"JSON 解析失败: {line}")
            return AgentResponse(
                content="响应解析失败：服务返回了无效的 JSON 数据。",
                sources=[],
                tool_calls=session.tool_calls,
            )

        except ClaudeSDKError as e:
            logger.error(f"Claude SDK 错误: {e}")
            return AgentResponse(
                content=f"SDK 错误: {str(e)}",
                sources=list(set(session.sources)),
                tool_calls=session.tool_calls,
            )

        except Exception as e:
            logger.exception(f"未知错误: {e}")
            return AgentResponse(
                content=f"查询失败: {str(e)}",
                sources=list(set(session.sources)),
                tool_calls=session.tool_calls,
            )

        return AgentResponse(
            content=final_result,
            sources=list(set(session.sources)),  # 去重
            tool_calls=session.tool_calls,
        )

    def _process_event(self, event: Any, session: SessionState) -> None:
        """处理 SDK 事件

        使用 isinstance() 检查事件类型，符合 SDK 最佳实践。
        """
        # 处理 AssistantMessage
        if AssistantMessage is not None and isinstance(event, AssistantMessage):
            for block in event.content:
                # TextBlock - 文本内容
                if TextBlock is not None and isinstance(block, TextBlock):
                    # 文本内容不需要特殊处理，最终结果在 ResultMessage 中
                    pass

                # ToolUseBlock - 工具调用
                elif ToolUseBlock is not None and isinstance(block, ToolUseBlock):
                    session.add_tool_call(
                        name=block.name,
                        input_data=block.input,
                    )
                    logger.debug(f"Tool call: {block.name}")

        # 从工具结果中提取来源
        if hasattr(event, "type") and getattr(event, "type", None) == "tool_result":
            content = getattr(event, "content", None)
            if content:
                self._extract_sources(content, session)

        # 处理 content 属性（可能包含工具结果）
        if hasattr(event, "content"):
            content = getattr(event, "content", None)
            if content and not isinstance(event, AssistantMessage):
                self._extract_sources(content, session)

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
        logger.debug(f"Session reset: {session_id or 'default'}")

    async def reset_all(self):
        """重置所有会话"""
        self._session_manager.reset_all()
        logger.debug("All sessions reset")

    def get_sessions(self) -> list[str]:
        """获取所有活跃会话 ID"""
        return self._session_manager.get_all_sessions()

    def get_session_info(self, session_id: str | None = None) -> dict | None:
        """获取会话信息"""
        return self._session_manager.get_session_info(session_id)
