"""Pydantic AI Subagent 实现

每个 Subagent 是一个独立的 Agent 实例，持有过滤后的 MCP 工具集。
Orchestrator 通过 Subagent 工具来调用它们。

架构:
    Subagent
        └── Agent (pydantic-ai)
                └── FilteredMCPServer (仅包含该 Subagent 需要的工具)
"""

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from loguru import logger

from grid_code.subagents.base import BaseSubagent, SubagentContext
from grid_code.subagents.config import SubagentConfig, SubagentType
from grid_code.subagents.result import SubagentResult

# Pydantic AI imports
try:
    from pydantic_ai import Agent
    from pydantic_ai.messages import ModelMessage

    HAS_PYDANTIC_AI = True
except ImportError:
    HAS_PYDANTIC_AI = False
    Agent = None  # type: ignore
    ModelMessage = None  # type: ignore

if TYPE_CHECKING:
    from pydantic_ai.mcp import MCPServerStdio


@dataclass
class SubagentDependencies:
    """Subagent 依赖注入"""

    reg_id: str | None = None
    chapter_scope: str | None = None
    hints: dict | None = None


class FilteredMCPToolset:
    """过滤的 MCP 工具集

    Pydantic AI 的 toolsets 接口代理，仅暴露配置中指定的工具。
    """

    def __init__(self, mcp_server: "MCPServerStdio", allowed_tools: set[str]):
        """初始化过滤工具集

        Args:
            mcp_server: 原始 MCP Server
            allowed_tools: 允许的工具名称集合
        """
        self._mcp_server = mcp_server
        self._allowed_tools = allowed_tools

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self._mcp_server.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self._mcp_server.__aexit__(exc_type, exc_val, exc_tb)

    def list_tools(self):
        """列出可用工具（过滤后）"""
        all_tools = self._mcp_server.list_tools()
        return [t for t in all_tools if t.name in self._allowed_tools]

    async def call_tool(self, name: str, arguments: dict) -> Any:
        """调用工具

        Args:
            name: 工具名称
            arguments: 工具参数

        Returns:
            工具返回结果

        Raises:
            ValueError: 工具不在允许列表中
        """
        if name not in self._allowed_tools:
            raise ValueError(f"Tool '{name}' is not allowed for this subagent")
        return await self._mcp_server.call_tool(name, arguments)


class BasePydanticSubagent(BaseSubagent):
    """Pydantic AI Subagent 基类

    每个 Subagent 持有：
    - 专用的 system prompt
    - 过滤后的 MCP 工具集
    - 独立的消息历史

    Attributes:
        config: Subagent 配置
        model: LLM 模型标识
        mcp_server: 过滤后的 MCP Server
    """

    def __init__(
        self,
        config: SubagentConfig,
        model: str,
        mcp_server: "MCPServerStdio",
    ):
        """初始化 Pydantic Subagent

        Args:
            config: Subagent 配置
            model: LLM 模型标识（如 'openai:gpt-4'）
            mcp_server: 原始 MCP Server（将被过滤）
        """
        if not HAS_PYDANTIC_AI:
            raise ImportError(
                "Pydantic AI not installed. Please run: pip install 'pydantic-ai>=1.0.0'"
            )

        super().__init__(config)
        self._model = model
        self._original_mcp_server = mcp_server

        # 创建过滤后的工具集
        self._filtered_toolset = FilteredMCPToolset(
            mcp_server, set(config.tools)
        )

        # 创建 Agent
        self._agent = Agent(
            self._model,
            deps_type=SubagentDependencies,
            system_prompt=config.system_prompt,
            toolsets=[self._filtered_toolset],
        )

        # 消息历史（每次执行后重置）
        self._message_history: list[ModelMessage] = []

        # 工具调用追踪
        self._tool_calls: list[dict] = []
        self._sources: list[str] = []

        # 连接状态
        self._connected = False

        logger.debug(
            f"PydanticSubagent '{self.name}' initialized with tools: {config.tools}"
        )

    @property
    def name(self) -> str:
        return self._config.name

    async def _ensure_connected(self) -> None:
        """确保 Agent 已连接"""
        if not self._connected:
            await self._agent.__aenter__()
            self._connected = True

    async def execute(self, context: SubagentContext) -> SubagentResult:
        """执行 Subagent

        Args:
            context: Subagent 上下文

        Returns:
            执行结果
        """
        await self._ensure_connected()

        # 重置状态
        self._tool_calls = []
        self._sources = list(context.parent_sources)

        # 构建查询消息
        query_parts = [context.query]
        if context.reg_id:
            query_parts.append(f"[规程: {context.reg_id}]")
        if context.chapter_scope:
            query_parts.append(f"[章节范围: {context.chapter_scope}]")
        if context.hints:
            hints_str = ", ".join(f"{k}={v}" for k, v in context.hints.items())
            query_parts.append(f"[提示: {hints_str}]")

        query = " ".join(query_parts)

        # 创建依赖
        deps = SubagentDependencies(
            reg_id=context.reg_id,
            chapter_scope=context.chapter_scope,
            hints=context.hints,
        )

        try:
            # 执行 Agent
            result = await self._agent.run(query, deps=deps)

            # 提取工具调用和来源
            self._extract_tool_calls_and_sources(result)

            return SubagentResult(
                agent_type=self._config.agent_type,
                success=True,
                content=result.output,
                sources=list(set(self._sources)),
                tool_calls=self._tool_calls,
            )

        except Exception as e:
            logger.exception(f"Subagent '{self.name}' execution error: {e}")
            return SubagentResult(
                agent_type=self._config.agent_type,
                success=False,
                content="",
                error=str(e),
                sources=list(set(self._sources)),
                tool_calls=self._tool_calls,
            )

    def _extract_tool_calls_and_sources(self, result: Any) -> None:
        """从结果中提取工具调用和来源"""
        for msg in result.all_messages():
            if hasattr(msg, "parts"):
                for part in msg.parts:
                    # ToolCallPart
                    if hasattr(part, "tool_name") and hasattr(part, "args"):
                        self._tool_calls.append({
                            "name": part.tool_name,
                            "input": part.args if isinstance(part.args, dict) else {},
                        })

                    # ToolReturnPart
                    if hasattr(part, "content"):
                        self._extract_sources_from_content(part.content)

    def _extract_sources_from_content(self, content: Any) -> None:
        """从内容中提取来源信息"""
        if content is None:
            return

        if isinstance(content, dict):
            if "source" in content and content["source"]:
                self._sources.append(str(content["source"]))
            for value in content.values():
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

    async def reset(self) -> None:
        """重置 Subagent 状态"""
        self._message_history = []
        self._tool_calls = []
        self._sources = []

    async def close(self) -> None:
        """关闭 Subagent"""
        if self._connected:
            await self._agent.__aexit__(None, None, None)
            self._connected = False


class SearchSubagent(BasePydanticSubagent):
    """搜索专家 Subagent

    专注于规程发现、目录导航和内容搜索。
    """

    pass


class TableSubagent(BasePydanticSubagent):
    """表格专家 Subagent

    专注于表格搜索、跨页合并和注释追踪。
    """

    pass


class ReferenceSubagent(BasePydanticSubagent):
    """引用专家 Subagent

    专注于交叉引用解析和引用内容提取。
    """

    pass


class DiscoverySubagent(BasePydanticSubagent):
    """语义发现专家 Subagent（可选）

    专注于相似内容发现和章节比较。
    """

    pass


# Subagent 类型映射
PYDANTIC_SUBAGENT_CLASSES: dict[SubagentType, type[BasePydanticSubagent]] = {
    SubagentType.SEARCH: SearchSubagent,
    SubagentType.TABLE: TableSubagent,
    SubagentType.REFERENCE: ReferenceSubagent,
    SubagentType.DISCOVERY: DiscoverySubagent,
}


def create_pydantic_subagent(
    config: SubagentConfig,
    model: str,
    mcp_server: "MCPServerStdio",
) -> BasePydanticSubagent:
    """创建 Pydantic Subagent 实例

    Args:
        config: Subagent 配置
        model: LLM 模型标识
        mcp_server: MCP Server

    Returns:
        对应类型的 Subagent 实例
    """
    subagent_class = PYDANTIC_SUBAGENT_CLASSES.get(
        config.agent_type, BasePydanticSubagent
    )
    return subagent_class(config, model, mcp_server)
