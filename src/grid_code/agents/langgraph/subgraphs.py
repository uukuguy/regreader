"""LangGraph Subgraphs 实现

每个 Subagent 对应一个独立的 Subgraph，实现上下文隔离。

架构:
    Subgraph
        └── StateGraph
                ├── agent (LLM 节点)
                └── tools (ToolNode，仅包含该 Subagent 需要的工具)
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

from grid_code.subagents.base import BaseSubagent, SubagentContext
from grid_code.subagents.config import SubagentConfig, SubagentType
from grid_code.subagents.result import SubagentResult

if TYPE_CHECKING:
    from grid_code.mcp import GridCodeMCPClient


class SubgraphState(TypedDict):
    """Subgraph 状态

    与 OrchestratorState 分离，实现上下文隔离。
    """

    messages: Annotated[list[BaseMessage], add_messages]
    """消息历史（自动累积）"""

    tool_calls: list[dict]
    """工具调用记录"""

    sources: list[str]
    """来源信息"""


class BaseSubgraph(BaseSubagent):
    """LangGraph Subgraph 基类

    每个 Subgraph 是独立的 StateGraph，持有：
    - 专用的 system prompt
    - 过滤后的工具集
    - 独立的消息历史

    Attributes:
        config: Subagent 配置
        llm: LLM 实例
        mcp_client: MCP 客户端（共享）
        graph: 编译后的 StateGraph
    """

    def __init__(
        self,
        config: SubagentConfig,
        llm: ChatOpenAI,
        mcp_client: "GridCodeMCPClient",
    ):
        """初始化 Subgraph

        Args:
            config: Subagent 配置
            llm: LLM 实例（共享）
            mcp_client: MCP 客户端（共享）
        """
        super().__init__(config)
        self._llm = llm
        self._mcp_client = mcp_client

        # 状态追踪
        self._tool_calls: list[dict] = []
        self._sources: list[str] = []

        # 过滤工具并构建图
        self._langchain_tools = self._filter_and_convert_tools()
        self._graph = self._build_graph()

        logger.debug(
            f"Subgraph '{self.name}' initialized with tools: "
            f"{[t.name for t in self._langchain_tools]}"
        )

    @property
    def name(self) -> str:
        return self._config.name

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

            # 创建工具执行函数
            async def tool_func(tool_name: str = tool_name, **kwargs) -> str:
                """执行 MCP 工具"""
                import json

                result = await self._mcp_client.call_tool(tool_name, kwargs)

                # 追踪工具调用
                self._tool_calls.append({
                    "name": tool_name,
                    "input": kwargs,
                    "output": result,
                })

                # 提取来源
                self._extract_sources(result)

                # 返回 JSON 字符串
                if isinstance(result, (dict, list)):
                    return json.dumps(result, ensure_ascii=False)
                return str(result) if result else ""

            # 从 input_schema 创建 Pydantic 模型
            schema = tool_def.get("input_schema", {})
            args_schema = self._create_args_schema(tool_name, schema)

            # 创建 StructuredTool
            structured_tool = StructuredTool(
                name=tool_name,
                description=tool_def.get("description", ""),
                func=lambda **kwargs: None,  # 同步占位
                coroutine=tool_func,  # 异步执行
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

    def _build_graph(self) -> StateGraph:
        """构建 Subgraph 的 StateGraph"""
        if not self._langchain_tools:
            # 没有工具时，创建简单的直接回复图
            builder = StateGraph(SubgraphState)
            builder.add_node("agent", self._simple_agent_node)
            builder.add_edge(START, "agent")
            builder.add_edge("agent", END)
            return builder.compile()

        # 绑定工具到 LLM
        llm_with_tools = self._llm.bind_tools(self._langchain_tools)

        # 定义 agent 节点
        async def agent_node(state: SubgraphState) -> dict:
            """Agent 节点：调用 LLM"""
            messages = state["messages"]

            # 确保有系统提示
            if not messages or not isinstance(messages[0], SystemMessage):
                messages = [SystemMessage(content=self._config.system_prompt)] + list(
                    messages
                )

            response = await llm_with_tools.ainvoke(messages)
            return {"messages": [response]}

        # 定义路由函数
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

        return builder.compile()

    async def _simple_agent_node(self, state: SubgraphState) -> dict:
        """简单 Agent 节点（无工具时使用）"""
        messages = state["messages"]

        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=self._config.system_prompt)] + list(
                messages
            )

        response = await self._llm.ainvoke(messages)
        return {"messages": [response]}

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

    async def execute(self, context: SubagentContext) -> SubagentResult:
        """执行 Subgraph

        Args:
            context: Subagent 上下文

        Returns:
            执行结果
        """
        # 重置状态
        self._tool_calls = []
        self._sources = list(context.parent_sources)

        # 构建查询消息（包含上下文提示）
        query_parts = [context.query]
        if context.reg_id:
            query_parts.append(f"[规程: {context.reg_id}]")
        if context.chapter_scope:
            query_parts.append(f"[章节范围: {context.chapter_scope}]")
        if context.hints:
            hints_str = ", ".join(f"{k}={v}" for k, v in context.hints.items())
            query_parts.append(f"[提示: {hints_str}]")

        query = " ".join(query_parts)

        # 执行图
        try:
            final_content = ""
            input_state: SubgraphState = {
                "messages": [HumanMessage(content=query)],
                "tool_calls": [],
                "sources": list(context.parent_sources),
            }

            # 执行到完成
            result_state = await self._graph.ainvoke(input_state)

            # 提取最终回答
            messages = result_state.get("messages", [])
            for msg in reversed(messages):
                if isinstance(msg, AIMessage) and not msg.tool_calls:
                    if isinstance(msg.content, str):
                        final_content = msg.content
                    elif isinstance(msg.content, list):
                        text_parts = []
                        for item in msg.content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                text_parts.append(item.get("text", ""))
                            elif isinstance(item, str):
                                text_parts.append(item)
                        final_content = "".join(text_parts)
                    break

            return SubagentResult(
                agent_type=self._config.agent_type,
                success=True,
                content=final_content,
                sources=list(set(self._sources)),
                tool_calls=self._tool_calls,
            )

        except Exception as e:
            logger.exception(f"Subgraph '{self.name}' execution error: {e}")
            return SubagentResult(
                agent_type=self._config.agent_type,
                success=False,
                content="",
                error=str(e),
                sources=list(set(self._sources)),
                tool_calls=self._tool_calls,
            )

    async def reset(self) -> None:
        """重置 Subgraph 状态"""
        self._tool_calls = []
        self._sources = []


class SearchSubgraph(BaseSubgraph):
    """搜索专家 Subgraph

    专注于规程发现、目录导航和内容搜索。
    工具：list_regulations, get_toc, smart_search, read_page_range
    """

    pass


class TableSubgraph(BaseSubgraph):
    """表格专家 Subgraph

    专注于表格搜索、跨页合并和注释追踪。
    工具：search_tables, get_table_by_id, lookup_annotation
    """

    pass


class ReferenceSubgraph(BaseSubgraph):
    """引用专家 Subgraph

    专注于交叉引用解析和引用内容提取。
    工具：resolve_reference, lookup_annotation, read_page_range
    """

    pass


class DiscoverySubgraph(BaseSubgraph):
    """语义发现专家 Subgraph（可选）

    专注于相似内容发现和章节比较。
    工具：find_similar_content, compare_sections
    """

    pass


# Subgraph 类型映射
SUBGRAPH_CLASSES: dict[SubagentType, type[BaseSubgraph]] = {
    SubagentType.SEARCH: SearchSubgraph,
    SubagentType.TABLE: TableSubgraph,
    SubagentType.REFERENCE: ReferenceSubgraph,
    SubagentType.DISCOVERY: DiscoverySubgraph,
}


def create_subgraph(
    config: SubagentConfig,
    llm: ChatOpenAI,
    mcp_client: "GridCodeMCPClient",
) -> BaseSubgraph:
    """创建 Subgraph 实例

    Args:
        config: Subagent 配置
        llm: LLM 实例
        mcp_client: MCP 客户端

    Returns:
        对应类型的 Subgraph 实例
    """
    subgraph_class = SUBGRAPH_CLASSES.get(config.agent_type, BaseSubgraph)
    return subgraph_class(config, llm, mcp_client)
