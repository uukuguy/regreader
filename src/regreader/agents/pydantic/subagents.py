"""Pydantic AI Subagent 实现

使用 Pydantic AI 原生的 Agent 委托模式:
- 每个 Subagent 是独立的 Agent 实例
- Orchestrator 通过 @tool 装饰器注册委托工具
- 使用 deps/usage 传递实现依赖注入和使用量追踪

架构:
    OrchestratorAgent (主协调器)
        └── @tool call_search_agent(ctx: RunContext[Deps], query: str) -> str
        └── @tool call_table_agent(ctx: RunContext[Deps], query: str) -> str
        └── @tool call_reference_agent(ctx: RunContext[Deps], query: str) -> str
        └── @tool call_discovery_agent(ctx: RunContext[Deps], query: str) -> str

    每个 @tool 内部调用:
        result = await subagent.run(query, deps=ctx.deps, usage=ctx.usage)
"""

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from loguru import logger

from regreader.subagents.config import SubagentConfig, SubagentType
from regreader.orchestrator.result import SubagentResult

# Pydantic AI imports
try:
    from pydantic_ai import Agent, RunContext
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.usage import Usage

    HAS_PYDANTIC_AI = True
except ImportError:
    HAS_PYDANTIC_AI = False
    Agent = None  # type: ignore
    RunContext = None  # type: ignore
    ModelMessage = None  # type: ignore
    Usage = None  # type: ignore

if TYPE_CHECKING:
    from pydantic_ai.mcp import MCPServerStdio


# ============================================================================
# Dependencies
# ============================================================================


@dataclass
class SubagentDependencies:
    """Subagent 共享依赖

    通过 ctx.deps 传递给所有 Subagent，实现依赖注入。

    Attributes:
        reg_id: 规程 ID
        mcp_server: 共享的 MCP Server
        hints: 额外提示信息
    """

    reg_id: str | None = None
    mcp_server: Any = None  # MCPServerStdio
    hints: dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Subagent Output
# ============================================================================


@dataclass
class SubagentOutput:
    """Subagent 输出结果

    用于 @tool 函数的返回值。

    Attributes:
        content: 回答内容
        sources: 来源列表
        tool_calls: 工具调用记录
        success: 是否成功
        error: 错误信息
    """

    content: str
    sources: list[str] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    success: bool = True
    error: str | None = None

    def to_result(self, agent_type: SubagentType) -> SubagentResult:
        """转换为 SubagentResult"""
        return SubagentResult(
            agent_type=agent_type,
            success=self.success,
            content=self.content,
            sources=self.sources,
            tool_calls=self.tool_calls,
            error=self.error,
        )


# ============================================================================
# Subagent Builder
# ============================================================================


class SubagentBuilder:
    """Pydantic AI Subagent 构建器

    创建独立的 Subagent Agent 实例，每个持有:
    - 专用的 system prompt
    - 过滤后的 MCP 工具集
    - 独立的执行上下文

    Attributes:
        config: Subagent 配置
        model: LLM 模型标识
    """

    def __init__(
        self,
        config: SubagentConfig,
        model: str,
    ):
        """初始化 Subagent 构建器

        Args:
            config: Subagent 配置
            model: LLM 模型标识（如 'openai:gpt-4'）
        """
        if not HAS_PYDANTIC_AI:
            raise ImportError(
                "Pydantic AI not installed. Please run: pip install 'pydantic-ai>=1.0.0'"
            )

        self._config = config
        self._model = model
        self._allowed_tools = set(config.tools)

        # 工具调用追踪（每次调用重置）
        self._tool_calls: list[dict] = []
        self._sources: list[str] = []

        logger.debug(
            f"SubagentBuilder '{config.name}' initialized with tools: {list(self._allowed_tools)}"
        )

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def agent_type(self) -> SubagentType:
        return self._config.agent_type

    @property
    def allowed_tools(self) -> set[str]:
        return self._allowed_tools

    def build(self, mcp_server: "MCPServerStdio") -> "Agent[SubagentDependencies, str]":
        """构建 Agent 实例

        Args:
            mcp_server: MCP Server

        Returns:
            配置好的 Agent 实例
        """
        # 创建过滤工具集的代理
        # 注意: Pydantic AI 的 MCP toolset 会自动暴露所有工具
        # 我们需要通过 tool_filter 参数过滤（如果支持）
        # 或在 system prompt 中指示只使用特定工具

        # 构建增强的 system prompt，明确指定可用工具
        enhanced_prompt = self._build_enhanced_prompt()

        agent = Agent(
            self._model,
            deps_type=SubagentDependencies,
            system_prompt=enhanced_prompt,
            mcp_servers=[mcp_server],  # 直接使用 MCP Server
        )

        return agent

    def _build_enhanced_prompt(self) -> str:
        """构建增强的系统提示词

        在原始提示词基础上添加工具使用限制。
        """
        tools_list = ", ".join(sorted(self._allowed_tools))
        tool_restriction = f"\n\n【可用工具】\n你只能使用以下工具: {tools_list}\n请不要尝试调用其他工具。"

        return self._config.system_prompt + tool_restriction

    def reset_tracking(self) -> None:
        """重置工具调用追踪"""
        self._tool_calls = []
        self._sources = []

    def get_tracking(self) -> tuple[list[dict], list[str]]:
        """获取工具调用追踪数据

        Returns:
            (tool_calls, sources) 元组
        """
        return self._tool_calls.copy(), self._sources.copy()

    async def invoke(
        self,
        agent: "Agent[SubagentDependencies, str]",
        query: str,
        deps: SubagentDependencies,
        usage: "Usage | None" = None,
    ) -> SubagentOutput:
        """调用 Subagent

        这是供 Orchestrator @tool 函数使用的便捷方法。

        Args:
            agent: 构建好的 Agent 实例
            query: 用户查询
            deps: 共享依赖
            usage: 使用量追踪对象

        Returns:
            SubagentOutput 结果
        """
        # 重置追踪
        self.reset_tracking()

        # 构建查询消息（包含上下文提示）
        query_parts = [query]
        if deps.reg_id:
            query_parts.append(f"[规程: {deps.reg_id}]")
        if deps.hints:
            hints_str = ", ".join(f"{k}={v}" for k, v in deps.hints.items())
            query_parts.append(f"[提示: {hints_str}]")

        full_query = " ".join(query_parts)

        try:
            # 执行 Agent（传递 usage 以聚合使用量）
            result = await agent.run(full_query, deps=deps, usage=usage)

            # 提取工具调用和来源
            self._extract_tool_calls_and_sources(result)

            return SubagentOutput(
                content=result.output if isinstance(result.output, str) else str(result.output),
                sources=list(set(self._sources)),
                tool_calls=self._tool_calls,
                success=True,
                error=None,
            )

        except Exception as e:
            logger.exception(f"Subagent '{self.name}' execution error: {e}")
            return SubagentOutput(
                content="",
                sources=list(set(self._sources)),
                tool_calls=self._tool_calls,
                success=False,
                error=str(e),
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


# ============================================================================
# Factory Function
# ============================================================================


def create_subagent_builder(
    config: SubagentConfig,
    model: str,
) -> SubagentBuilder:
    """创建 SubagentBuilder 实例

    Args:
        config: Subagent 配置
        model: LLM 模型标识

    Returns:
        SubagentBuilder 实例
    """
    return SubagentBuilder(config, model)


# ============================================================================
# Legacy Classes (保持向后兼容)
# ============================================================================

# 以下类已废弃，保留仅为向后兼容
# 请使用 SubagentBuilder 代替

from regreader.subagents.base import BaseSubagent, SubagentContext


class FilteredMCPToolset:
    """过滤的 MCP 工具集 (Legacy)

    已废弃: 不再需要此 workaround。
    Pydantic AI 原生支持 MCP Server，通过 system prompt 限制工具使用。
    """

    def __init__(self, mcp_server: "MCPServerStdio", allowed_tools: set[str]):
        self._mcp_server = mcp_server
        self._allowed_tools = allowed_tools

    async def __aenter__(self):
        await self._mcp_server.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._mcp_server.__aexit__(exc_type, exc_val, exc_tb)

    def list_tools(self):
        all_tools = self._mcp_server.list_tools()
        return [t for t in all_tools if t.name in self._allowed_tools]

    async def call_tool(self, name: str, arguments: dict) -> Any:
        if name not in self._allowed_tools:
            raise ValueError(f"Tool '{name}' is not allowed for this subagent")
        return await self._mcp_server.call_tool(name, arguments)


class BasePydanticSubagent(BaseSubagent):
    """Pydantic AI Subagent 基类 (Legacy)

    已废弃: 请使用 SubagentBuilder 代替。
    保留此类仅为向后兼容。
    """

    def __init__(
        self,
        config: SubagentConfig,
        model: str,
        mcp_server: "MCPServerStdio",
    ):
        super().__init__(config)
        self._builder = SubagentBuilder(config, model)
        self._mcp_server = mcp_server
        self._agent: Agent | None = None

    @property
    def name(self) -> str:
        return self._config.name

    async def execute(self, context: SubagentContext) -> SubagentResult:
        """执行 Subagent"""
        if self._agent is None:
            self._agent = self._builder.build(self._mcp_server)

        deps = SubagentDependencies(
            reg_id=context.reg_id,
            mcp_server=self._mcp_server,
            hints=context.hints or {},
        )

        output = await self._builder.invoke(
            self._agent,
            context.query,
            deps,
        )

        return output.to_result(self._config.agent_type)

    async def reset(self) -> None:
        """重置状态"""
        self._builder.reset_tracking()


class SearchSubagent(BasePydanticSubagent):
    """搜索专家 Subagent (Legacy)"""

    @property
    def name(self) -> str:
        """Subagent 标识名"""
        return "search"


class TableSubagent(BasePydanticSubagent):
    """表格专家 Subagent (Legacy)"""

    @property
    def name(self) -> str:
        """Subagent 标识名"""
        return "table"


class ReferenceSubagent(BasePydanticSubagent):
    """引用专家 Subagent (Legacy)"""

    @property
    def name(self) -> str:
        """Subagent 标识名"""
        return "reference"


class DiscoverySubagent(BasePydanticSubagent):
    """语义发现专家 Subagent (Legacy)"""

    @property
    def name(self) -> str:
        """Subagent 标识名"""
        return "discovery"


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
    """创建 Pydantic Subagent 实例 (Legacy)

    已废弃: 请使用 create_subagent_builder 代替。
    """
    subagent_class = PYDANTIC_SUBAGENT_CLASSES.get(
        config.agent_type, BasePydanticSubagent
    )
    return subagent_class(config, model, mcp_server)
