"""LangGraph Subgraphs 实现

每个 Subagent 对应一个独立的 Subgraph，使用 LangGraph 原生的子图组合模式。

架构:
    OrchestratorGraph (父图)
        ├── router (路由节点)
        ├── search_subgraph (搜索子图)
        ├── table_subgraph (表格子图)
        ├── reference_subgraph (引用子图)
        ├── discovery_subgraph (发现子图)
        └── aggregator (聚合节点)

关键特性:
    - 子图作为父图节点，通过 subgraph.invoke() 调用
    - 状态转换在节点函数中完成
    - 支持 checkpointer=True 实现子图独立记忆
    - 支持 subgraphs=True 实现流式输出
"""

from typing import TYPE_CHECKING, Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from loguru import logger
from pydantic import BaseModel, Field

from regreader.subagents.config import SubagentConfig, SubagentType

if TYPE_CHECKING:
    from regreader.mcp import RegReaderMCPClient


# ============================================================================
# Subgraph State Definitions
# ============================================================================


class SubgraphState(TypedDict):
    """Subgraph 内部状态

    与 OrchestratorState 分离，实现上下文隔离。
    """

    messages: Annotated[list[BaseMessage], add_messages]
    """消息历史（自动累积）"""

    query: str
    """原始查询"""

    reg_id: str | None
    """规程 ID"""

    hints: dict[str, Any]
    """提示信息"""


class SubgraphOutput(TypedDict):
    """Subgraph 输出结果

    用于父图节点函数的返回值。
    """

    content: str
    """最终回答内容"""

    sources: list[str]
    """来源信息"""

    tool_calls: list[dict]
    """工具调用记录"""

    success: bool
    """是否成功"""

    error: str | None
    """错误信息"""


# ============================================================================
# Subgraph Builder
# ============================================================================


class SubgraphBuilder:
    """Subgraph 构建器

    创建独立的 Subgraph，每个 Subgraph 持有:
    - 专用的 system prompt
    - 过滤后的工具集
    - 独立的消息历史

    Attributes:
        config: Subagent 配置
        llm: LLM 实例
        mcp_client: MCP 客户端（共享）
    """

    def __init__(
        self,
        config: SubagentConfig,
        llm: ChatOpenAI,
        mcp_client: "RegReaderMCPClient",
    ):
        """初始化 Subgraph 构建器

        Args:
            config: Subagent 配置
            llm: LLM 实例（共享）
            mcp_client: MCP 客户端（共享）
        """
        self._config = config
        self._llm = llm
        self._mcp_client = mcp_client

        # 过滤工具并转换为 LangChain 格式
        self._langchain_tools = self._filter_and_convert_tools()

        # 工具调用追踪（每次调用重置）
        self._tool_calls: list[dict] = []
        self._sources: list[str] = []

        logger.debug(
            f"SubgraphBuilder '{config.name}' initialized with tools: "
            f"{[t.name for t in self._langchain_tools]}"
        )

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def agent_type(self) -> SubagentType:
        return self._config.agent_type

    def _filter_and_convert_tools(self) -> list[StructuredTool]:
        """过滤并转换 MCP 工具为 LangChain 工具

        只保留配置中指定的工具。

        Returns:
            过滤后的 LangChain 工具列表
        """
        if self._mcp_client is None:
            return []

        allowed_tools = set(self._config.tools)
        mcp_tools = self._mcp_client.get_tools_for_langchain()
        langchain_tools = []

        for tool_def in mcp_tools:
            tool_name = tool_def["name"]

            # 过滤非允许的工具
            if tool_name not in allowed_tools:
                continue

            # 创建闭包捕获 tool_name
            def make_tool_func(captured_name: str):
                async def tool_func(**kwargs) -> str:
                    """执行 MCP 工具"""
                    import json

                    result = await self._mcp_client.call_tool(captured_name, kwargs)

                    # 追踪工具调用
                    self._tool_calls.append({
                        "name": captured_name,
                        "input": kwargs,
                        "output": result,
                    })

                    # 提取来源
                    self._extract_sources(result)

                    # 返回 JSON 字符串
                    if isinstance(result, (dict, list)):
                        return json.dumps(result, ensure_ascii=False)
                    return str(result) if result else ""

                return tool_func

            # 从 input_schema 创建 Pydantic 模型
            schema = tool_def.get("input_schema", {})
            args_schema = self._create_args_schema(tool_name, schema)

            # 创建 StructuredTool
            structured_tool = StructuredTool(
                name=tool_name,
                description=tool_def.get("description", ""),
                func=lambda **kwargs: None,  # 同步占位
                coroutine=make_tool_func(tool_name),  # 异步执行
                args_schema=args_schema,
            )
            langchain_tools.append(structured_tool)

        return langchain_tools

    def _create_args_schema(self, tool_name: str, schema: dict) -> type[BaseModel]:
        """从 JSON Schema 创建 Pydantic 模型"""
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))

        fields = {}
        for prop_name, prop_schema in properties.items():
            prop_type = prop_schema.get("type", "string")
            prop_desc = prop_schema.get("description", "")

            type_mapping = {
                "string": str,
                "integer": int,
                "number": float,
                "boolean": bool,
                "array": list,
                "object": dict,
            }
            python_type = type_mapping.get(prop_type, str)

            if prop_name in required:
                fields[prop_name] = (python_type, Field(description=prop_desc))
            else:
                fields[prop_name] = (
                    python_type | None,
                    Field(default=None, description=prop_desc),
                )

        model_name = f"{tool_name.title().replace('_', '')}Args"
        return type(
            model_name,
            (BaseModel,),
            {
                "__annotations__": {k: v[0] for k, v in fields.items()},
                **{k: v[1] for k, v in fields.items()},
            },
        )

    def _extract_sources(self, result: Any) -> None:
        """从工具结果中提取来源信息"""
        if result is None:
            return

        if isinstance(result, dict):
            if "source" in result and result["source"]:
                self._sources.append(str(result["source"]))
            for value in result.values():
                self._extract_sources(value)
        elif isinstance(result, list):
            for item in result:
                self._extract_sources(item)

    def build(self) -> Any:
        """构建并编译 Subgraph

        Returns:
            编译后的 Subgraph
        """
        if not self._langchain_tools:
            # 没有工具时，创建简单的直接回复图
            return self._build_simple_graph()

        return self._build_agentic_graph()

    def _build_simple_graph(self) -> Any:
        """构建简单图（无工具）"""

        async def agent_node(state: SubgraphState) -> dict:
            """Agent 节点：直接调用 LLM"""
            messages = list(state["messages"])

            # 确保有系统提示
            if not messages or not isinstance(messages[0], SystemMessage):
                messages = [SystemMessage(content=self._config.system_prompt)] + messages

            response = await self._llm.ainvoke(messages)
            return {"messages": [response]}

        builder = StateGraph(SubgraphState)
        builder.add_node("agent", agent_node)
        builder.add_edge(START, "agent")
        builder.add_edge("agent", END)

        return builder.compile()

    def _build_agentic_graph(self) -> Any:
        """构建 Agentic 图（有工具）"""
        # 绑定工具到 LLM
        llm_with_tools = self._llm.bind_tools(self._langchain_tools)

        async def agent_node(state: SubgraphState) -> dict:
            """Agent 节点：调用 LLM"""
            messages = list(state["messages"])

            # 确保有系统提示
            if not messages or not isinstance(messages[0], SystemMessage):
                messages = [SystemMessage(content=self._config.system_prompt)] + messages

            response = await llm_with_tools.ainvoke(messages)
            return {"messages": [response]}

        def should_continue(state: SubgraphState) -> Literal["tools", "__end__"]:
            """判断是否继续调用工具"""
            messages = state["messages"]
            last_message = messages[-1]

            if isinstance(last_message, AIMessage) and last_message.tool_calls:
                return "tools"
            return END

        # 构建 StateGraph
        builder = StateGraph(SubgraphState)
        builder.add_node("agent", agent_node)
        builder.add_node("tools", ToolNode(self._langchain_tools))

        builder.add_edge(START, "agent")
        builder.add_conditional_edges("agent", should_continue, ["tools", END])
        builder.add_edge("tools", "agent")

        # 编译时可以启用独立记忆
        return builder.compile()

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
        query: str,
        reg_id: str | None = None,
        hints: dict[str, Any] | None = None,
    ) -> SubgraphOutput:
        """调用 Subgraph

        这是供父图节点函数使用的便捷方法。

        Args:
            query: 用户查询
            reg_id: 规程 ID
            hints: 提示信息

        Returns:
            SubgraphOutput 结果
        """
        # 重置追踪
        self.reset_tracking()

        # 构建查询消息（包含上下文提示）
        query_parts = [query]
        if reg_id:
            query_parts.append(f"[规程: {reg_id}]")
        if hints:
            hints_str = ", ".join(f"{k}={v}" for k, v in hints.items())
            query_parts.append(f"[提示: {hints_str}]")

        full_query = " ".join(query_parts)

        # 构建初始状态
        input_state: SubgraphState = {
            "messages": [HumanMessage(content=full_query)],
            "query": query,
            "reg_id": reg_id,
            "hints": hints or {},
        }

        try:
            # 构建并执行图
            graph = self.build()
            result_state = await graph.ainvoke(input_state)

            # 提取最终回答
            final_content = self._extract_final_content(result_state)
            tool_calls, sources = self.get_tracking()

            return SubgraphOutput(
                content=final_content,
                sources=list(set(sources)),
                tool_calls=tool_calls,
                success=True,
                error=None,
            )

        except Exception as e:
            logger.exception(f"Subgraph '{self.name}' execution error: {e}")
            tool_calls, sources = self.get_tracking()

            return SubgraphOutput(
                content="",
                sources=list(set(sources)),
                tool_calls=tool_calls,
                success=False,
                error=str(e),
            )

    def _extract_final_content(self, result_state: dict) -> str:
        """从结果状态中提取最终内容"""
        messages = result_state.get("messages", [])

        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and not msg.tool_calls:
                if isinstance(msg.content, str):
                    return msg.content
                elif isinstance(msg.content, list):
                    text_parts = []
                    for item in msg.content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                        elif isinstance(item, str):
                            text_parts.append(item)
                    return "".join(text_parts)

        return ""


# ============================================================================
# Subgraph Factory
# ============================================================================


def create_subgraph_builder(
    config: SubagentConfig,
    llm: ChatOpenAI,
    mcp_client: "RegReaderMCPClient",
) -> SubgraphBuilder:
    """创建 SubgraphBuilder 实例

    Args:
        config: Subagent 配置
        llm: LLM 实例
        mcp_client: MCP 客户端

    Returns:
        SubgraphBuilder 实例
    """
    return SubgraphBuilder(config, llm, mcp_client)


# ============================================================================
# Legacy Classes (保持向后兼容)
# ============================================================================

# 以下类已废弃，保留仅为向后兼容
# 请使用 SubgraphBuilder 代替

from regreader.subagents.base import BaseSubagent, SubagentContext
from regreader.subagents.result import SubagentResult


class BaseSubgraph(BaseSubagent):
    """LangGraph Subgraph 基类 (Legacy)

    已废弃: 请使用 SubgraphBuilder 代替。
    保留此类仅为向后兼容。
    """

    def __init__(
        self,
        config: SubagentConfig,
        llm: ChatOpenAI,
        mcp_client: "RegReaderMCPClient",
    ):
        super().__init__(config)
        self._builder = SubgraphBuilder(config, llm, mcp_client)

    @property
    def name(self) -> str:
        return self._config.name

    async def execute(self, context: SubagentContext) -> SubagentResult:
        """执行 Subgraph"""
        output = await self._builder.invoke(
            context.query,
            context.reg_id,
            context.hints,
        )

        return SubagentResult(
            agent_type=self._config.agent_type,
            success=output["success"],
            content=output["content"],
            sources=output["sources"],
            tool_calls=output["tool_calls"],
            error=output["error"],
        )

    async def reset(self) -> None:
        """重置状态"""
        self._builder.reset_tracking()


class SearchSubgraph(BaseSubgraph):
    """搜索专家 Subgraph (Legacy)"""
    pass


class TableSubgraph(BaseSubgraph):
    """表格专家 Subgraph (Legacy)"""
    pass


class ReferenceSubgraph(BaseSubgraph):
    """引用专家 Subgraph (Legacy)"""
    pass


class DiscoverySubgraph(BaseSubgraph):
    """语义发现专家 Subgraph (Legacy)"""
    pass


SUBGRAPH_CLASSES: dict[SubagentType, type[BaseSubgraph]] = {
    SubagentType.SEARCH: SearchSubgraph,
    SubagentType.TABLE: TableSubgraph,
    SubagentType.REFERENCE: ReferenceSubgraph,
    SubagentType.DISCOVERY: DiscoverySubgraph,
}


def create_subgraph(
    config: SubagentConfig,
    llm: ChatOpenAI,
    mcp_client: "RegReaderMCPClient",
) -> BaseSubgraph:
    """创建 Subgraph 实例 (Legacy)

    已废弃: 请使用 create_subgraph_builder 代替。
    """
    subgraph_class = SUBGRAPH_CLASSES.get(config.agent_type, BaseSubgraph)
    return subgraph_class(config, llm, mcp_client)
