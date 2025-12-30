"""Pydantic AI Agent 实现

使用 Pydantic AI v1.0+ 框架实现 GridCode Agent。
通过 MCPServerStdio 直接连接 GridCode MCP Server，无需手动注册工具。

架构:
    PydanticAIAgent
        └── MCPServerStdio (toolsets)
                └── GridCode MCP Server (stdio)
                        └── PageStore (页面数据)
"""

from dataclasses import dataclass
from typing import Any

from loguru import logger

from grid_code.agents.base import AgentResponse, BaseGridCodeAgent
from grid_code.agents.mcp_config import MCP_SERVER_ARGS, get_mcp_command
from grid_code.agents.prompts import SYSTEM_PROMPT
from grid_code.config import get_settings

# Pydantic AI imports
try:
    from pydantic_ai import Agent, RunContext
    from pydantic_ai.mcp import MCPServerStdio
    from pydantic_ai.messages import ModelMessage

    HAS_PYDANTIC_AI = True
except ImportError:
    HAS_PYDANTIC_AI = False
    Agent = None  # type: ignore
    RunContext = None  # type: ignore
    MCPServerStdio = None  # type: ignore
    ModelMessage = None  # type: ignore
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
    ):
        """初始化 Pydantic AI Agent

        Args:
            reg_id: 默认规程标识（可选）
            model: 模型名称，格式为 'provider:model'
                   如 'anthropic:claude-sonnet-4-20250514'
                   默认使用配置文件中的 default_model
        """
        super().__init__(reg_id)

        if not HAS_PYDANTIC_AI:
            raise ImportError(
                "Pydantic AI not installed or outdated. "
                "Please run: pip install 'pydantic-ai>=1.0.0'"
            )

        settings = get_settings()

        # 解析模型配置
        self._model_name = self._resolve_model(model or settings.default_model)
        logger.debug(f"Using model: {self._model_name}")

        # 创建 MCP Server 连接（stdio 模式）
        self._mcp_server = MCPServerStdio(
            get_mcp_command(),
            args=MCP_SERVER_ARGS,
        )

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

        # 连接状态
        self._connected = False

        logger.info(f"PydanticAIAgent initialized: model={self._model_name}")

    def _resolve_model(self, model: str) -> str:
        """解析模型名称为 Pydantic AI 格式

        Pydantic AI 使用 'provider:model' 格式：
        - anthropic:claude-sonnet-4-20250514
        - openai:gpt-4o
        - google-gla:gemini-1.5-pro

        Args:
            model: 模型名称（可能带或不带 provider 前缀）

        Returns:
            标准化的模型名称
        """
        # 如果已经是 provider:model 格式，直接返回
        if ":" in model:
            return model

        # 根据模型名称推断 provider
        model_lower = model.lower()

        if "claude" in model_lower or "sonnet" in model_lower or "opus" in model_lower or "haiku" in model_lower:
            return f"anthropic:{model}"
        elif "gpt" in model_lower or "o1" in model_lower or "o3" in model_lower:
            return f"openai:{model}"
        elif "gemini" in model_lower:
            return f"google-gla:{model}"

        # 默认使用 Anthropic
        return f"anthropic:{model}"

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

        # 创建依赖
        deps = AgentDependencies(reg_id=self.reg_id)

        try:
            # 运行 Agent（传入消息历史以支持多轮对话）
            result = await self._agent.run(
                message,
                deps=deps,
                message_history=self._message_history if self._message_history else None,
            )

            # 更新消息历史
            self._message_history = result.all_messages()

            # 提取工具调用和来源
            self._extract_tool_calls_and_sources(result)

            return AgentResponse(
                content=result.output,
                sources=list(set(self._sources)),
                tool_calls=self._tool_calls,
            )

        except Exception as e:
            logger.exception(f"Agent error: {e}")
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
                import json
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
