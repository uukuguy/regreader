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
import time
import uuid
from typing import TYPE_CHECKING, Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from loguru import logger
from pydantic import BaseModel, Field

from grid_code.agents.base import AgentResponse, BaseGridCodeAgent
from grid_code.agents.callbacks import NullCallback, StatusCallback
from grid_code.agents.events import (
    iteration_event,
    response_complete_event,
    text_delta_event,
    thinking_event,
    tool_end_event,
    tool_start_event,
)
from grid_code.agents.mcp_connection import MCPConnectionConfig, get_mcp_manager
from grid_code.agents.memory import AgentMemory
from grid_code.agents.prompts import SYSTEM_PROMPT, SYSTEM_PROMPT_SIMPLE, SYSTEM_PROMPT_V2
from grid_code.agents.result_parser import parse_tool_result
from grid_code.config import get_settings

if TYPE_CHECKING:
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
        status_callback: StatusCallback | None = None,
    ):
        """初始化 LangGraph Agent

        Args:
            reg_id: 默认规程标识
            model: Claude 模型名称
            mcp_config: MCP 连接配置（可选，默认从全局配置创建）
            status_callback: 状态回调（可选），用于实时输出 Agent 运行状态
        """
        super().__init__(reg_id)

        settings = get_settings()
        self._model_name = model or settings.llm_model_name

        # 统一使用 OpenAI 兼容接口（与 pydantic_agent 一致）
        # 因为大多数模型服务都提供 OpenAI 兼容接口
        self._llm = ChatOpenAI(
            model=self._model_name,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            max_tokens=4096,
            streaming=True,  # 启用流式输出
        )

        logger.debug(
            f"LLM initialized: model={self._model_name}, "
            f"base_url={settings.llm_base_url}"
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

        # 状态回调
        self._callback = status_callback or NullCallback()

        # 迭代计数（用于状态显示）
        self._iteration_count: int = 0

        # 记忆系统（目录缓存 + 相关内容记忆）
        self._memory = AgentMemory()

        # 追踪上一工具结束时间（用于计算思考耗时）
        self._last_tool_end_time: float | None = None

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
        """构建系统提示词

        根据配置选择不同版本的提示词：
        - full: 完整版（向后兼容）
        - optimized: 优化版（默认，减少 token 消耗）
        - simple: 最简版（最快响应）

        同时注入记忆上下文（目录缓存提示 + 已获取的相关内容）
        """
        settings = get_settings()

        # 根据 prompt_mode 选择基础提示词
        if settings.prompt_mode == "full":
            base_prompt = SYSTEM_PROMPT
        elif settings.prompt_mode == "simple":
            base_prompt = SYSTEM_PROMPT_SIMPLE
        else:  # optimized
            base_prompt = SYSTEM_PROMPT_V2

        # 注入默认规程上下文
        if self.reg_id:
            base_prompt += (
                f"\n\n# 当前规程上下文\n"
                f"默认规程标识: {self.reg_id}\n"
                f"调用工具时如未指定 reg_id，请使用此默认值。"
            )

        # 注入目录缓存提示
        toc_hint = self._memory.get_toc_cache_hint()
        if toc_hint:
            base_prompt += toc_hint

        # 注入已获取的相关内容
        memory_context = self._memory.get_memory_context()
        if memory_context:
            base_prompt += f"\n\n{memory_context}"

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

                # 计算思考耗时（从上一工具结束到本工具开始）
                now = time.time()
                thinking_duration_ms = None
                if self._last_tool_end_time is not None:
                    thinking_duration_ms = (now - self._last_tool_end_time) * 1000
                    logger.debug(f"[LangGraph] thinking_duration_ms={thinking_duration_ms:.1f}")

                # 发送工具调用开始事件
                await self._callback.on_event(tool_start_event(tool_name, kwargs))

                # 记录开始时间
                start_time = time.time()

                result = await self._mcp_client.call_tool(tool_name, kwargs)

                # 计算执行耗时
                end_time = time.time()
                duration_ms = (end_time - start_time) * 1000

                # 更新上一工具结束时间
                self._last_tool_end_time = end_time

                # 追踪工具调用
                self._tool_calls.append({
                    "name": tool_name,
                    "input": kwargs,
                    "output": result,
                    "thinking_duration_ms": thinking_duration_ms,
                })

                # 提取来源
                sources_before = len(self._sources)
                self._extract_sources(result)
                new_sources = self._sources[sources_before:]

                # 使用结果解析器提取详细摘要
                summary = parse_tool_result(tool_name, result)

                # 发送工具调用完成事件（带详细摘要）
                await self._callback.on_event(
                    tool_end_event(
                        tool_name=tool_name,
                        duration_ms=duration_ms,
                        result_count=summary.result_count,
                        sources=new_sources,
                        tool_input=kwargs,
                        # 详细模式新增字段
                        result_type=summary.result_type,
                        chapter_count=summary.chapter_count,
                        page_sources=summary.page_sources,
                        content_preview=summary.content_preview,
                        thinking_duration_ms=thinking_duration_ms,
                    )
                )

                # 更新记忆系统
                self._update_memory(tool_name, result)

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
            # 增加迭代计数并发送事件
            self._iteration_count += 1
            if self._iteration_count > 1:
                # 从第2轮开始发送迭代事件（第1轮已经在 chat 中发送了 thinking 事件）
                await self._callback.on_event(iteration_event(self._iteration_count))

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

    def _update_memory(self, tool_name: str, result: Any) -> None:
        """根据工具结果更新记忆系统

        Args:
            tool_name: 工具名称
            result: 工具返回结果
        """
        # 解析 JSON 字符串
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return

        if not isinstance(result, dict):
            return

        if tool_name == "get_toc":
            # 缓存目录
            reg_id = result.get("reg_id", self.reg_id)
            if reg_id:
                self._memory.cache_toc(reg_id, result)

        elif tool_name == "smart_search":
            # 提取搜索结果
            results = result.get("results", [])
            self._memory.add_search_results(results)

        elif tool_name == "read_page_range":
            # 记录页面内容摘要
            content = result.get("content_markdown") or result.get("content")
            source = result.get("source", "")
            if content and source:
                self._memory.add_page_content(content, source)

        elif tool_name == "read_chapter_content":
            # 记录章节内容摘要
            content = result.get("content") or result.get("content_markdown")
            source = result.get("source", "")
            if content and source:
                self._memory.add_page_content(content, source, relevance=0.85)

    async def chat(self, message: str) -> AgentResponse:
        """与 Agent 对话

        使用 StateGraph 执行 ReAct 循环。
        通过 thread_id 支持多轮对话。
        支持流式输出 LLM 响应内容。

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
        self._iteration_count = 0
        self._last_tool_end_time = None  # 重置工具时间追踪

        # 记录开始时间
        start_time = time.time()

        # 发送思考开始事件
        await self._callback.on_event(thinking_event(start=True))

        # 配置（包含 thread_id）
        config = {"configurable": {"thread_id": self._thread_id}}

        # 执行图（使用流式处理）
        try:
            final_content = ""
            final_messages = []

            # 使用 astream_events 获取流式事件
            async for event in self._graph.astream_events(
                {"messages": [HumanMessage(content=message)]},
                config=config,
                version="v2",
            ):
                event_type = event.get("event", "")

                # 处理 LLM 流式输出
                if event_type == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        # 发送文本增量事件
                        if isinstance(chunk.content, str):
                            await self._callback.on_event(
                                text_delta_event(chunk.content)
                            )

                # 处理图执行结束
                elif event_type == "on_chain_end":
                    # 检查是否为最终输出
                    output = event.get("data", {}).get("output", {})
                    if isinstance(output, dict) and "messages" in output:
                        final_messages = output.get("messages", [])

            # 从最终消息中提取回答
            for msg in reversed(final_messages):
                if isinstance(msg, AIMessage) and not msg.tool_calls:
                    if isinstance(msg.content, str):
                        final_content = msg.content
                    elif isinstance(msg.content, list):
                        # content 可能是 blocks 列表
                        text_parts = []
                        for item in msg.content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                text_parts.append(item.get("text", ""))
                            elif isinstance(item, str):
                                text_parts.append(item)
                        final_content = "".join(text_parts)
                    break

            # 发送思考结束事件
            await self._callback.on_event(thinking_event(start=False))

            # 计算总耗时
            duration_ms = (time.time() - start_time) * 1000

            # 发送响应完成事件
            await self._callback.on_event(
                response_complete_event(
                    total_tool_calls=len(self._tool_calls),
                    total_sources=len(set(self._sources)),
                    duration_ms=duration_ms,
                )
            )

            return AgentResponse(
                content=final_content,
                sources=list(set(self._sources)),
                tool_calls=self._tool_calls,
            )

        except Exception as e:
            logger.exception(f"Graph execution error: {e}")

            # 发送思考结束事件（即使出错）
            await self._callback.on_event(thinking_event(start=False))

            return AgentResponse(
                content=f"查询失败: {str(e)}",
                sources=list(set(self._sources)),
                tool_calls=self._tool_calls,
            )

    async def reset(self) -> None:
        """重置对话历史

        生成新的 thread_id，开始新的会话。
        同时重置记忆系统。
        """
        self._thread_id = self._generate_thread_id()
        self._tool_calls = []
        self._sources = []
        self._last_tool_end_time = None
        self._memory.reset()  # 重置记忆系统
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
