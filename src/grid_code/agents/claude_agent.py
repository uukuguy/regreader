"""Claude Agent SDK 实现

使用 Claude Agent SDK 实现 GridCode Agent。
https://platform.claude.com/docs/en/agent-sdk/overview
"""

import sys
from typing import Any

from loguru import logger

from grid_code.agents.base import AgentResponse, BaseGridCodeAgent
from grid_code.agents.prompts import SYSTEM_PROMPT
from grid_code.config import get_settings

# Claude Agent SDK imports
try:
    from claude_agent_sdk import (
        ClaudeAgentOptions,
        ClaudeSDKClient,
        # Message types for isinstance checks
        AssistantMessage,
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
    logger.warning("claude-agent-sdk not installed. Run: pip install claude-agent-sdk")


class ClaudeAgent(BaseGridCodeAgent):
    """基于 Claude Agent SDK 的 Agent 实现

    使用 Claude Agent SDK 的 ClaudeSDKClient 执行 agent loop，
    通过 MCP Server 连接 GridCode 工具。

    工具命名规则: mcp__{server_name}__{tool_name}
    例如: mcp__gridcode__get_toc, mcp__gridcode__smart_search
    """

    def __init__(
        self,
        reg_id: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
    ):
        """
        初始化 Claude Agent

        Args:
            reg_id: 默认规程标识
            model: Claude 模型名称 (haiku, sonnet, opus)
            api_key: Anthropic API Key (通过环境变量 ANTHROPIC_API_KEY 设置)
        """
        super().__init__(reg_id)

        if not HAS_CLAUDE_SDK:
            raise ImportError(
                "Claude Agent SDK not installed. "
                "Please run: pip install claude-agent-sdk"
            )

        settings = get_settings()
        self._model = model or settings.default_model

        # SDK 使用环境变量 ANTHROPIC_API_KEY，此处仅验证
        api_key = api_key or settings.anthropic_api_key
        if not api_key:
            raise ValueError(
                "未配置 Anthropic API Key。"
                "请设置环境变量 ANTHROPIC_API_KEY"
            )

        # 使用 ClaudeSDKClient 支持多轮对话
        self._client: ClaudeSDKClient | None = None
        self._session_id: str = "gridcode-session"

        # Tool call records
        self._tool_calls: list[dict] = []
        self._sources: list[str] = []
        self._assembled_text: str = ""

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
        return {
            "gridcode": {
                "type": "stdio",
                "command": sys.executable,
                "args": ["-m", "grid_code.cli", "serve", "--transport", "stdio"],
            }
        }

    def _get_allowed_tools(self) -> list[str]:
        """获取允许使用的工具列表

        GridCode MCP Server 提供的工具:
        - mcp__gridcode__get_toc: 获取目录
        - mcp__gridcode__smart_search: 混合检索
        - mcp__gridcode__read_page_range: 读取页面
        - mcp__gridcode__list_regulations: 列出规程
        """
        return [
            "mcp__gridcode__get_toc",
            "mcp__gridcode__smart_search",
            "mcp__gridcode__read_page_range",
            "mcp__gridcode__list_regulations",
        ]

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

    def _build_options(self) -> ClaudeAgentOptions:
        """构建 Agent 选项"""
        return ClaudeAgentOptions(
            system_prompt=self._build_system_prompt(),
            mcp_servers=self._get_mcp_config(),
            allowed_tools=self._get_allowed_tools(),
            model=self._model,
            max_turns=20,  # 允许多轮工具调用
            permission_mode="bypassPermissions",  # 自动执行工具
        )

    async def chat(self, message: str) -> AgentResponse:
        """
        与 Agent 对话

        使用 ClaudeSDKClient 作为上下文管理器，确保连接正确清理。

        Args:
            message: 用户消息

        Returns:
            AgentResponse
        """
        # Reset per-query tracking
        self._tool_calls = []
        self._sources = []
        self._assembled_text = ""

        final_result = ""

        try:
            # 使用上下文管理器确保连接正确清理
            async with ClaudeSDKClient(options=self._build_options()) as client:
                # 发送查询
                await client.query(message, session_id=self._session_id)

                # 接收响应
                async for event in client.receive_response():
                    self._process_event(event)

                    # 检查最终结果 (ResultMessage)
                    if ResultMessage is not None and isinstance(event, ResultMessage):
                        final_result = event.result or self._assembled_text
                        break

                # 如果没有通过 ResultMessage 获取，使用组装的文本
                if not final_result:
                    final_result = self._assembled_text

        except Exception as e:
            logger.error(f"Agent query failed: {e}")
            return AgentResponse(
                content=f"查询失败: {str(e)}",
                sources=[],
                tool_calls=self._tool_calls,
            )

        return AgentResponse(
            content=final_result,
            sources=list(set(self._sources)),  # 去重
            tool_calls=self._tool_calls,
        )

    def _process_event(self, event: Any) -> None:
        """处理 SDK 事件

        使用 isinstance() 检查事件类型，符合 SDK 最佳实践。
        """
        # 处理 AssistantMessage
        if AssistantMessage is not None and isinstance(event, AssistantMessage):
            for block in event.content:
                # TextBlock - 文本内容
                if TextBlock is not None and isinstance(block, TextBlock):
                    self._assembled_text += block.text

                # ToolUseBlock - 工具调用
                elif ToolUseBlock is not None and isinstance(block, ToolUseBlock):
                    tool_call = {
                        "name": block.name,
                        "input": block.input,
                    }
                    self._tool_calls.append(tool_call)
                    logger.debug(f"Tool call: {block.name}")

        # 从工具结果中提取来源（通过 hasattr 因为 ToolResultBlock 结构可能变化）
        if hasattr(event, "type") and getattr(event, "type", None) == "tool_result":
            content = getattr(event, "content", None)
            if content:
                self._extract_sources(content)

    def _extract_sources(self, result: Any) -> None:
        """从工具结果中提取来源信息"""
        if isinstance(result, dict):
            if "source" in result:
                self._sources.append(result["source"])
            # 递归检查嵌套内容
            for value in result.values():
                self._extract_sources(value)
        elif isinstance(result, list):
            for item in result:
                self._extract_sources(item)
        elif isinstance(result, str):
            # 尝试解析 JSON 字符串
            try:
                import json
                parsed = json.loads(result)
                self._extract_sources(parsed)
            except (json.JSONDecodeError, TypeError):
                pass

    async def reset(self):
        """重置对话历史

        由于使用上下文管理器，客户端连接会自动清理。
        此方法仅重置内部状态。
        """
        self._tool_calls = []
        self._sources = []
        self._assembled_text = ""
        logger.debug("Agent session reset")
