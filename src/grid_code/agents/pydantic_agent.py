"""Pydantic AI Agent 实现

使用 Pydantic AI 框架实现 GridCode Agent，通过 MCP 协议调用工具。
"""

from typing import Any

from loguru import logger
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIModel

from grid_code.agents.base import AgentResponse, BaseGridCodeAgent
from grid_code.agents.prompts import SYSTEM_PROMPT
from grid_code.config import get_settings
from grid_code.mcp import GridCodeMCPClient


class AgentDependencies(BaseModel):
    """Agent 依赖注入"""
    reg_id: str | None = None
    mcp_client: Any = None  # GridCodeMCPClient


class PydanticAIAgent(BaseGridCodeAgent):
    """基于 Pydantic AI 的 Agent 实现

    通过 MCP 协议连接 GridCode MCP Server，
    支持多模型切换（Claude、GPT 等）。

    架构:
        PydanticAIAgent
            └── MCP Client (stdio)
                    └── GridCode MCP Server
                            └── PageStore (页面数据)
    """

    def __init__(
        self,
        reg_id: str | None = None,
        model: str | None = None,
        provider: str = "anthropic",
    ):
        """
        初始化 Pydantic AI Agent

        Args:
            reg_id: 默认规程标识
            model: 模型名称
            provider: 模型提供商 ('anthropic', 'openai')
        """
        super().__init__(reg_id)

        settings = get_settings()
        self._model_name = model or settings.default_model
        self.provider = provider
        self._tool_calls: list[dict] = []
        self._sources: list[str] = []

        # MCP 客户端（延迟初始化）
        self._mcp_client: GridCodeMCPClient | None = None

        # 创建模型实例
        if provider == "anthropic":
            api_key = settings.anthropic_api_key
            if not api_key:
                raise ValueError("未配置 Anthropic API Key")
            model_instance = AnthropicModel(self._model_name, api_key=api_key)
        elif provider == "openai":
            api_key = settings.openai_api_key
            if not api_key:
                raise ValueError("未配置 OpenAI API Key")
            model_instance = OpenAIModel(self._model_name, api_key=api_key)
        else:
            raise ValueError(f"不支持的 provider: {provider}")

        # 创建 Agent（带系统提示）
        self.agent = Agent(
            model_instance,
            system_prompt=self._build_system_prompt(),
            deps_type=AgentDependencies,
        )

        # 注册 MCP 工具
        self._register_mcp_tools()

    @property
    def name(self) -> str:
        return f"PydanticAIAgent({self.provider})"

    @property
    def model(self) -> str:
        return self._model_name

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        base_prompt = SYSTEM_PROMPT
        if self.reg_id:
            return base_prompt + f"\n\n# 当前规程上下文\n默认规程标识: {self.reg_id}"
        return base_prompt

    def _register_mcp_tools(self):
        """注册 MCP 工具到 Agent

        这些工具作为代理，实际调用通过 MCP 客户端执行。
        """

        @self.agent.tool
        async def get_toc(ctx: RunContext[AgentDependencies], reg_id: str) -> dict:
            """获取安规的章节目录树及页码范围。

            在开始搜索前，应先调用此工具了解规程的整体结构。

            Args:
                reg_id: 规程标识，如 'angui_2024'
            """
            return await self._call_mcp_tool(ctx, "get_toc", {"reg_id": reg_id})

        @self.agent.tool
        async def smart_search(
            ctx: RunContext[AgentDependencies],
            query: str,
            reg_id: str,
            chapter_scope: str | None = None,
            limit: int = 10,
        ) -> list[dict]:
            """在安规中执行混合检索（关键词+语义）。

            结合全文检索和语义向量检索，返回最相关的内容片段。

            Args:
                query: 搜索查询，如 '母线失压处理'
                reg_id: 规程标识
                chapter_scope: 限定章节范围（可选）
                limit: 返回结果数量限制
            """
            # 使用默认 reg_id
            if ctx.deps.reg_id and not reg_id:
                reg_id = ctx.deps.reg_id

            result = await self._call_mcp_tool(ctx, "smart_search", {
                "query": query,
                "reg_id": reg_id,
                "chapter_scope": chapter_scope,
                "limit": limit,
            })

            # 收集来源
            if isinstance(result, list):
                for item in result:
                    if isinstance(item, dict) and "source" in item:
                        self._sources.append(item["source"])

            return result

        @self.agent.tool
        async def read_page_range(
            ctx: RunContext[AgentDependencies],
            reg_id: str,
            start_page: int,
            end_page: int,
        ) -> dict:
            """读取连续页面的完整 Markdown 内容。

            自动处理跨页表格拼接。单次最多读取 10 页。

            Args:
                reg_id: 规程标识
                start_page: 起始页码
                end_page: 结束页码
            """
            if ctx.deps.reg_id and not reg_id:
                reg_id = ctx.deps.reg_id

            result = await self._call_mcp_tool(ctx, "read_page_range", {
                "reg_id": reg_id,
                "start_page": start_page,
                "end_page": end_page,
            })

            # 收集来源
            if isinstance(result, dict) and "source" in result:
                self._sources.append(result["source"])

            return result

        @self.agent.tool
        async def list_regulations(ctx: RunContext[AgentDependencies]) -> list[dict]:
            """列出所有已入库的规程。"""
            return await self._call_mcp_tool(ctx, "list_regulations", {})

    async def _call_mcp_tool(
        self,
        ctx: RunContext[AgentDependencies],
        name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """通过 MCP 调用工具"""
        mcp_client = ctx.deps.mcp_client
        if mcp_client is None:
            raise RuntimeError("MCP client not available in context")

        logger.debug(f"Calling MCP tool: {name} with args: {arguments}")

        result = await mcp_client.call_tool(name, arguments)

        # 记录工具调用
        self._tool_calls.append({
            "name": name,
            "input": arguments,
            "output": result,
        })

        return result

    async def _ensure_mcp_connected(self) -> None:
        """确保 MCP 客户端已连接"""
        if self._mcp_client is None:
            self._mcp_client = GridCodeMCPClient()
            await self._mcp_client.connect()
            logger.debug("MCP client connected")

    async def chat(self, message: str) -> AgentResponse:
        """
        与 Agent 对话

        Pydantic AI 自动处理多轮工具调用循环。

        Args:
            message: 用户消息

        Returns:
            AgentResponse
        """
        # 确保 MCP 连接
        await self._ensure_mcp_connected()

        # 重置调用记录
        self._tool_calls = []
        self._sources = []

        # 创建依赖
        deps = AgentDependencies(
            reg_id=self.reg_id,
            mcp_client=self._mcp_client,
        )

        # 运行 Agent（自动处理多轮工具调用）
        result = await self.agent.run(message, deps=deps)

        return AgentResponse(
            content=result.data,
            sources=list(set(self._sources)),
            tool_calls=self._tool_calls,
        )

    async def reset(self):
        """重置对话历史"""
        self._tool_calls = []
        self._sources = []

    async def close(self):
        """关闭 MCP 连接"""
        if self._mcp_client:
            await self._mcp_client.disconnect()
            self._mcp_client = None

    async def __aenter__(self) -> "PydanticAIAgent":
        """异步上下文管理器"""
        await self._ensure_mcp_connected()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器"""
        await self.close()
