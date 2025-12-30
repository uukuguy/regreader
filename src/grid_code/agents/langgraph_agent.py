"""LangGraph Agent 实现

使用 LangGraph StateGraph 实现 GridCode Agent。
基于标准 ReAct 模式，支持多轮对话和状态持久化。

架构:
    LangGraphAgent
        └── StateGraph
                ├── agent (LLM 节点)
                └── tools (ToolNode)
                        └── MCP Client
                                └── GridCode MCP Server
"""

import json
import uuid
from typing import Annotated, Any, Literal, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from loguru import logger
from pydantic import BaseModel, Field

from grid_code.agents.base import AgentResponse, BaseGridCodeAgent
from grid_code.agents.mcp_connection import MCPConnectionConfig, get_mcp_manager
from grid_code.agents.prompts import SYSTEM_PROMPT
from grid_code.config import get_settings
from grid_code.mcp import GridCodeMCPClient


class AgentState(TypedDict):
    """Agent 状态

    LangGraph 使用 TypedDict 定义状态结构。
    messages 使用 add_messages 注解实现消息累积。
    """

    messages: Annotated[list[BaseMessage], add_messages]
    """消息历史（自动累积）"""


class LangGraphAgent(BaseGridCodeAgent):
    """基于 LangGraph StateGraph 的 Agent 实现

    使用标准 ReAct 模式：
    1. agent 节点调用 LLM
    2. 如果 LLM 返回工具调用，转到 tools 节点
    3. tools 节点执行工具，返回结果给 agent
    4. 重复直到 LLM 返回最终回答

    特性:
    - StateGraph 工作流
    - InMemorySaver 状态持久化
    - 多会话支持（通过 thread_id）
    - MCP 工具动态加载
    - 来源追踪

    Usage:
        async with LangGraphAgent(reg_id="angui_2024") as agent:
            response = await agent.chat("母线失压如何处理？")
            print(response.content)

            # 多轮对话（同一会话）
            response2 = await agent.chat("还有其他注意事项吗？")

            # 新会话
            await agent.reset()
            response3 = await agent.chat("什么是安规？")
    """

    def __init__(
        self,
        reg_id: str | None = None,
        model: str | None = None,
        mcp_config: MCPConnectionConfig | None = None,
    ):
        """初始化 LangGraph Agent

        Args:
            reg_id: 默认规程标识
            model: Claude 模型名称
            mcp_config: MCP 连接配置（可选，默认从全局配置创建）
        """
        super().__init__(reg_id)

        settings = get_settings()
        self._model_name = model or settings.default_model

        api_key = settings.anthropic_api_key
        if not api_key:
            raise ValueError("未配置 Anthropic API Key")

        # 创建 LLM
        self._llm = ChatAnthropic(
            model=self._model_name,
            api_key=api_key,
            max_tokens=4096,
        )

        # MCP 连接管理器
        self._mcp_manager = get_mcp_manager(mcp_config)

        # MCP 客户端（延迟初始化）
        self._mcp_client: GridCodeMCPClient | None = None
        self._langchain_tools: list[StructuredTool] = []

        # StateGraph 和 checkpointer
        self._graph: StateGraph | None = None
        self._checkpointer = InMemorySaver()

        # 当前会话 ID
        self._thread_id: str = self._generate_thread_id()

        # 工具调用追踪（单次查询）
        self._tool_calls: list[dict] = []
        self._sources: list[str] = []

        logger.info(
            f"LangGraphAgent initialized: model={self._model_name}, "
            f"mcp_transport={self._mcp_manager.config.transport}"
        )

    def _generate_thread_id(self) -> str:
        """生成新的会话 ID"""
        return f"gridcode-{uuid.uuid4().hex[:8]}"

    @property
    def name(self) -> str:
        return "LangGraphAgent"

    @property
    def model(self) -> str:
        return self._model_name

    @property
    def thread_id(self) -> str:
        """当前会话 ID"""
        return self._thread_id

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        base_prompt = SYSTEM_PROMPT
        if self.reg_id:
            context = (
                f"\n\n# 当前规程上下文\n"
                f"默认规程标识: {self.reg_id}\n"
                f"调用工具时如未指定 reg_id，请使用此默认值。"
            )
            return base_prompt + context
        return base_prompt

    async def _ensure_mcp_connected(self) -> None:
        """确保 MCP 客户端已连接并构建工具"""
        if self._mcp_client is None:
            # 通过统一管理器获取 MCP 客户端
            self._mcp_client = self._mcp_manager.get_langgraph_client()
            await self._mcp_client.connect()

            # 将 MCP 工具转换为 LangChain StructuredTool
            self._langchain_tools = self._convert_mcp_tools()

            # 构建 StateGraph
            self._build_graph()

            logger.debug(
                f"MCP connected ({self._mcp_manager.config.transport}), "
                f"tools: {[t.name for t in self._langchain_tools]}"
            )

    def _convert_mcp_tools(self) -> list[StructuredTool]:
        """将 MCP 工具转换为 LangChain StructuredTool

        Returns:
            LangChain 工具列表
        """
        if self._mcp_client is None:
            return []

        mcp_tools = self._mcp_client.get_tools_for_langchain()
        langchain_tools = []

        for tool_def in mcp_tools:
            # 创建工具执行函数（闭包捕获 tool_name）
            tool_name = tool_def["name"]

            async def tool_func(tool_name: str = tool_name, **kwargs) -> str:
                """执行 MCP 工具"""
                # 如果有默认 reg_id，自动填充
                if self.reg_id and "reg_id" in kwargs and not kwargs.get("reg_id"):
                    kwargs["reg_id"] = self.reg_id

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
        """从 JSON Schema 创建 Pydantic 模型

        Args:
            tool_name: 工具名称
            schema: JSON Schema

        Returns:
            Pydantic 模型类
        """
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))

        # 动态创建字段
        fields = {}
        for prop_name, prop_schema in properties.items():
            prop_type = prop_schema.get("type", "string")
            prop_desc = prop_schema.get("description", "")

            # 映射 JSON Schema 类型到 Python 类型
            type_mapping = {
                "string": str,
                "integer": int,
                "number": float,
                "boolean": bool,
                "array": list,
                "object": dict,
            }
            python_type = type_mapping.get(prop_type, str)

            # 是否可选
            if prop_name in required:
                fields[prop_name] = (python_type, Field(description=prop_desc))
            else:
                fields[prop_name] = (
                    python_type | None,
                    Field(default=None, description=prop_desc),
                )

        # 动态创建 Pydantic 模型
        model_name = f"{tool_name.title().replace('_', '')}Args"
        return type(model_name, (BaseModel,), {"__annotations__": {k: v[0] for k, v in fields.items()}, **{k: v[1] for k, v in fields.items()}})

    def _build_graph(self) -> None:
        """构建 StateGraph"""
        # 绑定工具到 LLM
        llm_with_tools = self._llm.bind_tools(self._langchain_tools)

        # 定义 agent 节点
        async def agent_node(state: AgentState) -> dict:
            """Agent 节点：调用 LLM"""
            # 添加系统提示
            messages = state["messages"]
            if not messages or not isinstance(messages[0], SystemMessage):
                messages = [SystemMessage(content=self._build_system_prompt())] + list(messages)

            response = await llm_with_tools.ainvoke(messages)
            return {"messages": [response]}

        # 定义路由函数
        def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
            """判断是否继续调用工具"""
            messages = state["messages"]
            last_message = messages[-1]

            # 如果 LLM 返回工具调用，转到 tools 节点
            if isinstance(last_message, AIMessage) and last_message.tool_calls:
                return "tools"

            # 否则结束
            return END

        # 构建 StateGraph
        builder = StateGraph(AgentState)

        # 添加节点
        builder.add_node("agent", agent_node)
        builder.add_node("tools", ToolNode(self._langchain_tools))

        # 添加边
        builder.add_edge(START, "agent")
        builder.add_conditional_edges("agent", should_continue, ["tools", END])
        builder.add_edge("tools", "agent")

        # 编译图（带 checkpointer）
        self._graph = builder.compile(checkpointer=self._checkpointer)

        logger.debug("StateGraph built successfully")

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

    async def chat(self, message: str) -> AgentResponse:
        """与 Agent 对话

        使用 StateGraph 执行 ReAct 循环。
        通过 thread_id 支持多轮对话。

        Args:
            message: 用户消息

        Returns:
            AgentResponse
        """
        # 确保 MCP 连接和图构建
        await self._ensure_mcp_connected()

        if self._graph is None:
            raise RuntimeError("StateGraph not built")

        # 重置单次查询的追踪
        self._tool_calls = []
        self._sources = []

        # 配置（包含 thread_id）
        config = {"configurable": {"thread_id": self._thread_id}}

        # 执行图
        try:
            result = await self._graph.ainvoke(
                {"messages": [HumanMessage(content=message)]},
                config=config,
            )

            # 提取最终回答
            final_content = ""
            messages = result.get("messages", [])
            for msg in reversed(messages):
                if isinstance(msg, AIMessage) and not msg.tool_calls:
                    final_content = msg.content
                    break

            return AgentResponse(
                content=final_content,
                sources=list(set(self._sources)),
                tool_calls=self._tool_calls,
            )

        except Exception as e:
            logger.exception(f"Graph execution error: {e}")
            return AgentResponse(
                content=f"查询失败: {str(e)}",
                sources=list(set(self._sources)),
                tool_calls=self._tool_calls,
            )

    async def reset(self) -> None:
        """重置对话历史

        生成新的 thread_id，开始新的会话。
        """
        self._thread_id = self._generate_thread_id()
        self._tool_calls = []
        self._sources = []
        logger.debug(f"Session reset, new thread_id: {self._thread_id}")

    def new_session(self) -> str:
        """创建新会话并返回会话 ID

        Returns:
            新的会话 ID
        """
        self._thread_id = self._generate_thread_id()
        return self._thread_id

    def switch_session(self, thread_id: str) -> None:
        """切换到指定会话

        Args:
            thread_id: 会话 ID
        """
        self._thread_id = thread_id
        logger.debug(f"Switched to session: {thread_id}")

    async def get_session_history(self) -> list[BaseMessage]:
        """获取当前会话的消息历史

        Returns:
            消息历史列表
        """
        if self._graph is None:
            return []

        config = {"configurable": {"thread_id": self._thread_id}}
        state = await self._graph.aget_state(config)

        if state and state.values:
            return state.values.get("messages", [])
        return []

    async def close(self) -> None:
        """关闭 MCP 连接"""
        if self._mcp_client:
            await self._mcp_client.disconnect()
            self._mcp_client = None
            self._langchain_tools = []
            self._graph = None
            logger.debug("MCP client disconnected")

    async def __aenter__(self) -> "LangGraphAgent":
        """异步上下文管理器入口"""
        await self._ensure_mcp_connected()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        await self.close()
