"""LangGraph Agent 实现

基于 agentex 框架的 LangGraph Agent。
"""

from __future__ import annotations

import json
import time
import uuid
from typing import TYPE_CHECKING, Annotated, Any, Literal, TypedDict

from loguru import logger

from ...agentex.agent import BaseAgent
from ...agentex.types import AgentResponse as AgentexResponse, Context
from ...agents.prompts import (
    get_full_prompt,
    get_optimized_prompt_with_domain,
    get_simple_prompt,
)
from ...agents.shared.callbacks import StatusCallback
from ...agents.shared.mcp_connection import MCPConnectionConfig, get_mcp_manager
from ...agents.shared.result_parser import format_result_summary, parse_tool_result
from ...core.config import get_settings
from ...storage import PageStore
from ..base import AgentResponse, RegReaderAgent
from ..config import LangGraphAgentConfig, RegReaderConfig
from ..events import EventAdapter

if TYPE_CHECKING:
    from ...mcp import RegReaderMCPClient

# LangGraph imports
try:
    import httpx
    from langchain_core.messages import (
        AIMessage,
        BaseMessage,
        HumanMessage,
        SystemMessage,
    )
    from langchain_core.tools import StructuredTool
    from langchain_openai import ChatOpenAI
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.graph.message import add_messages
    from langgraph.prebuilt import ToolNode
    from pydantic import BaseModel, Field

    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False
    httpx = None  # type: ignore
    AIMessage = None  # type: ignore
    BaseMessage = None  # type: ignore
    HumanMessage = None  # type: ignore
    SystemMessage = None  # type: ignore
    StructuredTool = None  # type: ignore
    ChatOpenAI = None  # type: ignore
    InMemorySaver = None  # type: ignore
    END = None  # type: ignore
    START = None  # type: ignore
    StateGraph = None  # type: ignore
    add_messages = None  # type: ignore
    ToolNode = None  # type: ignore
    BaseModel = None  # type: ignore
    Field = None  # type: ignore


if HAS_LANGGRAPH:
    class AgentState(TypedDict):
        """Agent 状态"""
        messages: Annotated[list[BaseMessage], add_messages]


class LangGraphAgent(RegReaderAgent):
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
    """

    def __init__(
        self,
        config: LangGraphAgentConfig | RegReaderConfig | None = None,
        reg_id: str | None = None,
        model: str | None = None,
        mcp_config: MCPConnectionConfig | None = None,
        status_callback: StatusCallback | None = None,
    ):
        """初始化 LangGraph Agent

        Args:
            config: Agent 配置
            reg_id: 默认规程标识
            model: 模型名称
            mcp_config: MCP 连接配置
            status_callback: 状态回调
        """
        if not HAS_LANGGRAPH:
            raise ImportError(
                "LangGraph not installed. "
                "Please run: pip install langgraph langchain-openai"
            )

        # 构建配置
        if config is None:
            config = LangGraphAgentConfig()

        # 如果传入的是 RegReaderConfig，转换为 LangGraphAgentConfig
        if not isinstance(config, LangGraphAgentConfig):
            config = LangGraphAgentConfig(
                reg_id=config.reg_id,
                enable_memory=config.enable_memory,
                enable_toc_cache=config.enable_toc_cache,
                prompt_mode=config.prompt_mode,
                mcp_config=config.mcp_config,
                status_callback=config.status_callback,
                model=config.model,
                system_prompt=config.system_prompt,
                max_iterations=config.max_iterations,
                timeout_seconds=config.timeout_seconds,
            )

        # 覆盖配置中的值
        if mcp_config is not None:
            config.mcp_config = mcp_config
        if status_callback is not None:
            config.status_callback = status_callback

        super().__init__(config=config, reg_id=reg_id, status_callback=status_callback)

        settings = get_settings()

        # 获取模型名称
        model_name = model or config.model or settings.llm_model_name
        self._model_name = model_name

        # 检测是否为 Ollama 后端
        self._is_ollama = settings.is_ollama_backend()

        # 配置 LLM
        llm_base_url = settings.llm_base_url
        if self._is_ollama:
            if not llm_base_url.endswith("/v1"):
                llm_base_url = llm_base_url.rstrip("/") + "/v1"

            self._ollama_http_client = httpx.AsyncClient(
                transport=httpx.AsyncHTTPTransport(),
            )
            self._llm = ChatOpenAI(
                model=model_name,
                api_key=settings.llm_api_key or "ollama",
                base_url=llm_base_url,
                max_tokens=4096,
                streaming=True,
                http_async_client=self._ollama_http_client,
            )
        else:
            self._ollama_http_client = None
            self._llm = ChatOpenAI(
                model=model_name,
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                max_tokens=4096,
                streaming=True,
            )

        # 获取 MCP 连接管理器
        self._mcp_manager = get_mcp_manager(config.mcp_config)

        # PageStore 实例
        self._page_store = PageStore(settings.pages_dir)
        self._regulations_cache: list[dict] | None = None

        # MCP 客户端（延迟初始化）
        self._mcp_client: RegReaderMCPClient | None = None
        self._langchain_tools: list[StructuredTool] = []

        # StateGraph 和 checkpointer
        self._graph: StateGraph | None = None
        self._checkpointer = InMemorySaver()

        # 当前会话 ID
        self._thread_id: str = self._generate_thread_id()

        # 工具调用追踪
        self._tool_calls: list[dict] = []
        self._sources: list[str] = []

        # 迭代计数
        self._iteration_count: int = 0

        # 追踪上一工具结束时间
        self._last_tool_end_time: float | None = None

        # 连接状态
        self._connected = False

        logger.info(
            f"LangGraphAgent (v2) initialized: model={self._model_name}, "
            f"mcp_transport={self._mcp_manager.config.transport}"
        )

    def _generate_thread_id(self) -> str:
        """生成新的会话 ID"""
        return f"regreader-{uuid.uuid4().hex[:8]}"

    @property
    def name(self) -> str:
        """Agent 名称"""
        return "LangGraphAgent"

    @property
    def model(self) -> str:
        """使用的模型名称"""
        return self._model_name

    @property
    def thread_id(self) -> str:
        """当前会话 ID"""
        return self._thread_id

    async def _create_agent(self) -> BaseAgent:
        """创建底层 agentex Agent

        LangGraphAgent 直接使用 LangGraph，不通过 agentex 框架。
        """
        return None  # type: ignore

    def _get_regulations(self) -> list[dict]:
        """获取规程列表（带缓存）"""
        if self._regulations_cache is None:
            regulations = self._page_store.list_regulations()
            self._regulations_cache = [
                {
                    "reg_id": r.reg_id,
                    "title": r.title,
                    "keywords": r.keywords,
                    "scope": r.scope,
                    "description": r.description,
                }
                for r in regulations
            ]
        return self._regulations_cache

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        settings = get_settings()
        include_advanced = getattr(settings, "enable_advanced_tools", False)
        regulations = self._get_regulations()

        if self._config.prompt_mode == "full":
            base_prompt = get_full_prompt(include_advanced, regulations)
        elif self._config.prompt_mode == "simple":
            base_prompt = get_simple_prompt()
        else:
            base_prompt = get_optimized_prompt_with_domain(include_advanced, regulations)

        if self.reg_id:
            base_prompt += f"\n\n# 当前规程\n默认规程: {self.reg_id}"

        if self._memory:
            toc_hint = self._memory.get_toc_cache_hint()
            if toc_hint:
                base_prompt += toc_hint

            memory_context = self._memory.get_memory_context()
            if memory_context:
                base_prompt += f"\n\n{memory_context}"

        return base_prompt

    async def _ensure_connected(self) -> None:
        """确保 MCP 客户端已连接并构建工具"""
        if not self._connected:
            # 通过统一管理器获取 MCP 客户端
            self._mcp_client = self._mcp_manager.get_langgraph_client()
            await self._mcp_client.connect()

            # 将 MCP 工具转换为 LangChain StructuredTool
            self._langchain_tools = self._convert_mcp_tools()

            # 构建 StateGraph
            self._build_graph()

            self._connected = True

            logger.debug(
                f"MCP connected ({self._mcp_manager.config.transport}), "
                f"tools: {[t.name for t in self._langchain_tools]}"
            )

    def _convert_mcp_tools(self) -> list[StructuredTool]:
        """将 MCP 工具转换为 LangChain StructuredTool"""
        if self._mcp_client is None:
            return []

        mcp_tools = self._mcp_client.get_tools_for_langchain()
        langchain_tools = []

        for tool_def in mcp_tools:
            tool_name = tool_def["name"]

            async def tool_func(tool_name: str = tool_name, **kwargs) -> str:
                """执行 MCP 工具"""
                if self.reg_id and "reg_id" in kwargs and not kwargs.get("reg_id"):
                    kwargs["reg_id"] = self.reg_id

                now = time.time()
                thinking_duration_ms = None
                if self._last_tool_end_time is not None:
                    thinking_duration_ms = (now - self._last_tool_end_time) * 1000

                # 发送工具调用开始事件
                await self._callback.on_event(
                    EventAdapter.create_tool_start_event(tool_name, kwargs)
                )

                start_time = time.time()
                result = await self._mcp_client.call_tool(tool_name, kwargs)

                end_time = time.time()
                duration_ms = (end_time - start_time) * 1000
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
                self._extract_sources_from_content(result)
                new_sources = self._sources[sources_before:]

                # 使用结果解析器
                summary = parse_tool_result(tool_name, result)
                result_summary_str = format_result_summary(summary, new_sources)

                # 发送工具调用完成事件
                await self._callback.on_event(
                    EventAdapter.create_tool_end_event(tool_name, result, duration_ms)
                )

                # 更新记忆系统
                self._update_memory(tool_name, result)

                if isinstance(result, (dict, list)):
                    return json.dumps(result, ensure_ascii=False)
                return str(result) if result else ""

            # 从 input_schema 创建 Pydantic 模型
            schema = tool_def.get("input_schema", {})
            args_schema = self._create_args_schema(tool_name, schema)

            structured_tool = StructuredTool(
                name=tool_name,
                description=tool_def.get("description", ""),
                func=lambda **kwargs: None,
                coroutine=tool_func,
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

    def _build_graph(self) -> None:
        """构建 StateGraph"""
        llm_with_tools = self._llm.bind_tools(self._langchain_tools)

        async def agent_node(state: AgentState) -> dict:
            """Agent 节点：调用 LLM"""
            self._iteration_count += 1

            messages = state["messages"]
            if not messages or not isinstance(messages[0], SystemMessage):
                messages = [SystemMessage(content=self._build_system_prompt())] + list(messages)

            response = await llm_with_tools.ainvoke(messages)
            return {"messages": [response]}

        def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
            """判断是否继续调用工具"""
            messages = state["messages"]
            last_message = messages[-1]

            if isinstance(last_message, AIMessage) and last_message.tool_calls:
                return "tools"

            return END

        builder = StateGraph(AgentState)
        builder.add_node("agent", agent_node)
        builder.add_node("tools", ToolNode(self._langchain_tools))

        builder.add_edge(START, "agent")
        builder.add_conditional_edges("agent", should_continue, ["tools", END])
        builder.add_edge("tools", "agent")

        self._graph = builder.compile(checkpointer=self._checkpointer)

    def _extract_sources_from_content(self, content: Any) -> None:
        """从内容中提取来源信息"""
        if content is None:
            return

        if isinstance(content, dict):
            if "source" in content and content["source"]:
                self._sources.append(str(content["source"]))

            for key, value in content.items():
                if key != "source":
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

    def _update_memory(self, tool_name: str, result: Any) -> None:
        """更新记忆系统"""
        if not self._memory:
            return

        if isinstance(result, str):
            try:
                result = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return

        if not isinstance(result, dict):
            return

        if tool_name == "get_toc":
            reg_id = result.get("reg_id", self.reg_id)
            if reg_id:
                self._memory.cache_toc(reg_id, result)

        elif tool_name == "smart_search":
            results = result.get("result") or result.get("results", [])
            self._memory.add_search_results(results, self.reg_id)

    async def chat(
        self,
        message: str,
        session_id: str | None = None,
    ) -> AgentResponse:
        """与 Agent 对话"""
        await self._ensure_connected()

        if self._graph is None:
            raise RuntimeError("StateGraph not built")

        # 获取或创建会话
        session = self._session_manager.get_or_create(session_id)
        session.reset_per_query()

        # 重置单次查询状态
        self._tool_calls = []
        self._sources = []
        self._iteration_count = 0
        self._last_tool_end_time = None

        start_time = time.time()

        await self._callback.on_event(EventAdapter.create_thinking_event(start=True))

        config = {"configurable": {"thread_id": self._thread_id}}

        try:
            final_content = ""
            final_messages = []

            try:
                async for event in self._graph.astream_events(
                    {"messages": [HumanMessage(content=message)]},
                    config=config,
                    version="v2",
                ):
                    event_type = event.get("event", "")

                    if event_type == "on_chat_model_stream":
                        chunk = event.get("data", {}).get("chunk")
                        if chunk and hasattr(chunk, "content") and chunk.content:
                            if isinstance(chunk.content, str):
                                await self._callback.on_event(
                                    EventAdapter.create_text_delta_event(chunk.content)
                                )

                    elif event_type == "on_chain_end":
                        output = event.get("data", {}).get("output", {})
                        if isinstance(output, dict) and "messages" in output:
                            final_messages = output.get("messages", [])

            except Exception as streaming_error:
                logger.warning(f"Streaming failed, falling back: {streaming_error}")

                result = await self._graph.ainvoke(
                    {"messages": [HumanMessage(content=message)]},
                    config=config,
                )
                final_messages = result.get("messages", [])

            # 从最终消息中提取回答
            for msg in reversed(final_messages):
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

            await self._callback.on_event(EventAdapter.create_thinking_event(start=False))

            duration_ms = (time.time() - start_time) * 1000

            await self._callback.on_event(
                EventAdapter.create_response_complete_event(
                    content=final_content,
                    sources=list(set(self._sources)),
                )
            )

            # 同步到会话
            for tc in self._tool_calls:
                session.add_tool_call(
                    name=tc.get("name", "unknown"),
                    input_data=tc.get("input", {}),
                    output=tc.get("output"),
                )
            for source in self._sources:
                session.add_source(source)

            return AgentResponse(
                content=final_content,
                sources=list(set(self._sources)),
                tool_calls=self._tool_calls,
            )

        except Exception as e:
            logger.exception(f"Graph execution error: {e}")
            await self._callback.on_event(EventAdapter.create_thinking_event(start=False))

            return AgentResponse(
                content=f"查询失败: {str(e)}",
                sources=list(set(self._sources)),
                tool_calls=self._tool_calls,
            )

    async def reset(self, session_id: str | None = None) -> None:
        """重置对话历史"""
        self._session_manager.reset(session_id)
        self._thread_id = self._generate_thread_id()
        self._tool_calls = []
        self._sources = []
        self._last_tool_end_time = None
        if self._memory:
            self._memory.clear_query_context()

    def new_session(self) -> str:
        """创建新会话并返回会话 ID"""
        self._thread_id = self._generate_thread_id()
        return self._thread_id

    def switch_session(self, thread_id: str) -> None:
        """切换到指定会话"""
        self._thread_id = thread_id

    async def get_session_history(self) -> list[BaseMessage]:
        """获取当前会话的消息历史"""
        if self._graph is None:
            return []

        config = {"configurable": {"thread_id": self._thread_id}}
        state = await self._graph.aget_state(config)

        if state and state.values:
            return state.values.get("messages", [])
        return []

    async def close(self) -> None:
        """关闭 Agent 连接"""
        if self._mcp_client:
            await self._mcp_client.disconnect()
            self._mcp_client = None
            self._langchain_tools = []
            self._graph = None

        if self._ollama_http_client is not None:
            await self._ollama_http_client.aclose()
            self._ollama_http_client = None

        self._connected = False

    async def __aenter__(self) -> "LangGraphAgent":
        """异步上下文管理器入口"""
        await self._ensure_connected()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        await self.close()
