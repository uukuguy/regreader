"""LangGraph Orchestrator 实现

使用 LangGraph 原生的父图-子图模式协调多个 Subgraph 的执行。

架构:
    OrchestratorGraph (父图)
        ├── router (路由节点) - 分析查询意图，决定调用哪些子图
        ├── search_subgraph (搜索子图)
        ├── table_subgraph (表格子图)
        ├── reference_subgraph (引用子图)
        ├── discovery_subgraph (发现子图)
        └── aggregator (聚合节点) - 合并所有子图结果

关键特性:
    - 子图作为父图节点，通过节点函数调用 subgraph.invoke()
    - 状态转换在节点函数中完成（父图状态 <-> 子图状态）
    - 条件边实现动态路由
    - 支持顺序和并行执行模式
"""

import asyncio
import time
import uuid
from typing import TYPE_CHECKING, Annotated, Any, Literal, TypedDict

import httpx
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from loguru import logger

from regreader.agents.base import AgentResponse, BaseRegReaderAgent
from regreader.agents.callbacks import NullCallback, StatusCallback
from regreader.agents.events import (
    response_complete_event,
    text_delta_event,
    thinking_event,
)
from regreader.agents.langgraph.subgraphs import (
    SubgraphBuilder,
    SubgraphOutput,
    create_subgraph_builder,
)
from regreader.agents.llm_timing import LLMTimingCollector
from regreader.agents.mcp_connection import MCPConnectionConfig, get_mcp_manager
from regreader.config import get_settings
from regreader.orchestrator.aggregator import ResultAggregator
from regreader.orchestrator.analyzer import QueryAnalyzer, QueryIntent
from regreader.subagents.config import (
    DISCOVERY_AGENT_CONFIG,
    REFERENCE_AGENT_CONFIG,
    SEARCH_AGENT_CONFIG,
    TABLE_AGENT_CONFIG,
    SubagentType,
)
from regreader.subagents.prompts import inject_prompt_to_config
from regreader.subagents.result import SubagentResult

# 在模块加载时注入提示词到配置
inject_prompt_to_config()

if TYPE_CHECKING:
    from regreader.mcp import RegReaderMCPClient


# ============================================================================
# Orchestrator State Definitions
# ============================================================================


class OrchestratorState(TypedDict):
    """Orchestrator 父图状态

    这是父图的状态，与子图状态（SubgraphState）分离。
    """

    messages: Annotated[list[BaseMessage], add_messages]
    """消息历史"""

    query: str
    """原始用户查询"""

    reg_id: str | None
    """规程 ID"""

    intent: QueryIntent | None
    """查询意图分析结果"""

    selected_subgraphs: list[str]
    """选中的子图列表"""

    subgraph_results: dict[str, SubgraphOutput]
    """各子图的执行结果"""

    final_content: str
    """最终聚合内容"""

    all_sources: list[str]
    """所有来源"""

    all_tool_calls: list[dict]
    """所有工具调用"""


# ============================================================================
# LangGraph Orchestrator
# ============================================================================


class LangGraphOrchestrator(BaseRegReaderAgent):
    """LangGraph 协调器

    使用 LangGraph 原生父图-子图模式协调多个专家代理。

    工作流程:
    1. router 节点: QueryAnalyzer 分析查询意图，选择子图
    2. subgraph 节点: 执行选中的子图（顺序或并行）
    3. aggregator 节点: 聚合所有子图结果

    特性:
    - 原生子图组合：子图作为父图节点，通过 invoke() 调用
    - 状态隔离：父图状态和子图状态分离
    - 灵活路由：基于意图分析的条件边
    - 结果聚合：合并多个子图的结果

    Usage:
        async with LangGraphOrchestrator(reg_id="angui_2024") as agent:
            response = await agent.chat("表6-2中注1的内容是什么？")
            print(response.content)
    """

    def __init__(
        self,
        reg_id: str | None = None,
        model: str | None = None,
        mcp_config: MCPConnectionConfig | None = None,
        status_callback: StatusCallback | None = None,
        mode: str = "sequential",
        enabled_subagents: list[str] | None = None,
    ):
        """初始化 LangGraph 协调器

        Args:
            reg_id: 默认规程标识
            model: LLM 模型名称
            mcp_config: MCP 连接配置
            status_callback: 状态回调
            mode: 执行模式（"sequential" 或 "parallel"）
            enabled_subagents: 启用的 Subagent 列表（默认全部启用，除 discovery）
        """
        super().__init__(reg_id)

        settings = get_settings()
        self._model_name = model or settings.llm_model_name
        self._is_ollama = settings.is_ollama_backend()
        self._mode = mode

        # 确定启用的 Subagent
        if enabled_subagents is None:
            enabled_subagents = ["search", "table", "reference"]
        self._enabled_subagents = set(enabled_subagents)

        # 状态回调（需要在 LLM 创建前设置）
        self._callback = status_callback or NullCallback()

        # 初始化 LLM
        self._llm = self._create_llm()

        # MCP 连接管理器
        self._mcp_manager = get_mcp_manager(mcp_config)

        # MCP 客户端（延迟初始化）
        self._mcp_client: RegReaderMCPClient | None = None

        # Subgraph Builders（延迟初始化）
        self._subgraph_builders: dict[SubagentType, SubgraphBuilder] = {}

        # 协调组件
        self._analyzer = QueryAnalyzer()
        self._aggregator = ResultAggregator()

        # 父图（延迟初始化）
        self._orchestrator_graph: Any = None

        # 会话 ID
        self._thread_id: str = self._generate_thread_id()

        # 工具调用追踪
        self._tool_calls: list[dict] = []
        self._sources: list[str] = []

        logger.info(
            f"LangGraphOrchestrator initialized: model={self._model_name}, "
            f"mode={self._mode}, enabled_subagents={self._enabled_subagents}"
        )

    def _create_llm(self) -> ChatOpenAI:
        """创建 LLM 实例"""
        settings = get_settings()
        llm_base_url = settings.llm_base_url

        if self._is_ollama:
            if not llm_base_url.endswith("/v1"):
                llm_base_url = llm_base_url.rstrip("/") + "/v1"

            self._timing_collector = LLMTimingCollector(callback=self._callback)
            self._ollama_http_client = httpx.AsyncClient(
                transport=httpx.AsyncHTTPTransport(),
                event_hooks={
                    "request": [self._timing_collector.on_request],
                    "response": [self._timing_collector.on_response],
                },
            )
            return ChatOpenAI(
                model=self._model_name,
                api_key=settings.llm_api_key or "ollama",
                base_url=llm_base_url,
                max_tokens=4096,
                streaming=True,
                http_async_client=self._ollama_http_client,
            )
        else:
            self._ollama_http_client = None
            self._timing_collector = None
            return ChatOpenAI(
                model=self._model_name,
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                max_tokens=4096,
                streaming=True,
            )

    def _generate_thread_id(self) -> str:
        """生成新的会话 ID"""
        return f"orchestrator-{uuid.uuid4().hex[:8]}"

    @property
    def name(self) -> str:
        return "LangGraphOrchestrator"

    @property
    def model(self) -> str:
        return self._model_name

    @property
    def thread_id(self) -> str:
        return self._thread_id

    async def _ensure_initialized(self) -> None:
        """确保组件已初始化"""
        if self._mcp_client is None:
            # 连接 MCP
            self._mcp_client = self._mcp_manager.get_langgraph_client()
            await self._mcp_client.connect()

            # 创建 Subgraph Builders
            self._subgraph_builders = self._create_subgraph_builders()

            # 构建父图
            self._orchestrator_graph = self._build_orchestrator_graph()

            logger.debug(
                f"Orchestrator initialized with subgraphs: "
                f"{list(self._subgraph_builders.keys())}"
            )

    def _create_subgraph_builders(self) -> dict[SubagentType, SubgraphBuilder]:
        """创建 SubgraphBuilder 实例"""
        builders = {}

        # 配置映射
        configs = {
            SubagentType.SEARCH: SEARCH_AGENT_CONFIG,
            SubagentType.TABLE: TABLE_AGENT_CONFIG,
            SubagentType.REFERENCE: REFERENCE_AGENT_CONFIG,
            SubagentType.DISCOVERY: DISCOVERY_AGENT_CONFIG,
        }

        for agent_type, config in configs.items():
            # 检查是否启用
            if agent_type.value not in self._enabled_subagents:
                continue

            if not config.enabled:
                continue

            # 创建 SubgraphBuilder
            builder = create_subgraph_builder(config, self._llm, self._mcp_client)
            builders[agent_type] = builder

        return builders

    def _build_orchestrator_graph(self) -> Any:
        """构建 Orchestrator 父图

        父图结构:
            START -> router -> [subgraph nodes] -> aggregator -> END
        """
        # 获取可用的子图类型
        available_types = list(self._subgraph_builders.keys())

        # ====================================================================
        # 定义节点函数
        # ====================================================================

        async def router_node(state: OrchestratorState) -> dict:
            """路由节点：分析意图并选择子图"""
            query = state["query"]

            # 分析意图
            intent = await self._analyzer.analyze(query)
            logger.debug(
                f"Query intent: primary={intent.primary_type}, "
                f"secondary={intent.secondary_types}"
            )

            # 确定要调用的子图
            selected = []

            # 添加主要子图
            if intent.primary_type in self._subgraph_builders:
                selected.append(intent.primary_type.value)

            # 添加次要子图
            for agent_type in intent.secondary_types:
                if (
                    agent_type in self._subgraph_builders
                    and agent_type.value not in selected
                ):
                    selected.append(agent_type.value)

            # 如果没有匹配，回退到 SearchAgent
            if not selected and SubagentType.SEARCH in self._subgraph_builders:
                selected.append(SubagentType.SEARCH.value)

            return {
                "intent": intent,
                "selected_subgraphs": selected,
            }

        async def execute_subgraphs_node(state: OrchestratorState) -> dict:
            """执行子图节点

            根据 mode 配置决定顺序或并行执行。
            """
            selected = state["selected_subgraphs"]
            query = state["query"]
            reg_id = state["reg_id"]
            intent = state["intent"]
            hints = intent.hints if intent else {}

            results: dict[str, SubgraphOutput] = {}
            all_sources: list[str] = []
            all_tool_calls: list[dict] = []

            if self._mode == "parallel":
                # 并行执行
                tasks = []
                for type_value in selected:
                    agent_type = SubagentType(type_value)
                    builder = self._subgraph_builders[agent_type]
                    tasks.append(builder.invoke(query, reg_id, hints))

                outputs = await asyncio.gather(*tasks, return_exceptions=True)

                for i, output in enumerate(outputs):
                    type_value = selected[i]
                    if isinstance(output, Exception):
                        results[type_value] = SubgraphOutput(
                            content="",
                            sources=[],
                            tool_calls=[],
                            success=False,
                            error=str(output),
                        )
                    else:
                        results[type_value] = output
                        all_sources.extend(output["sources"])
                        all_tool_calls.extend(output["tool_calls"])
            else:
                # 顺序执行
                for type_value in selected:
                    agent_type = SubagentType(type_value)
                    builder = self._subgraph_builders[agent_type]

                    output = await builder.invoke(query, reg_id, hints)
                    results[type_value] = output
                    all_sources.extend(output["sources"])
                    all_tool_calls.extend(output["tool_calls"])

            return {
                "subgraph_results": results,
                "all_sources": all_sources,
                "all_tool_calls": all_tool_calls,
            }

        async def aggregator_node(state: OrchestratorState) -> dict:
            """聚合节点：合并子图结果"""
            results = state["subgraph_results"]
            query = state["query"]

            # 转换为 SubagentResult 列表
            subagent_results = []
            for type_value, output in results.items():
                agent_type = SubagentType(type_value)
                subagent_results.append(
                    SubagentResult(
                        agent_type=agent_type,
                        success=output["success"],
                        content=output["content"],
                        sources=output["sources"],
                        tool_calls=output["tool_calls"],
                        error=output["error"],
                    )
                )

            # 使用 ResultAggregator 聚合
            aggregated = self._aggregator.aggregate(subagent_results, query)

            return {
                "final_content": aggregated.content,
            }

        # ====================================================================
        # 构建父图
        # ====================================================================

        builder = StateGraph(OrchestratorState)

        # 添加节点
        builder.add_node("router", router_node)
        builder.add_node("execute_subgraphs", execute_subgraphs_node)
        builder.add_node("aggregator", aggregator_node)

        # 添加边
        builder.add_edge(START, "router")
        builder.add_edge("router", "execute_subgraphs")
        builder.add_edge("execute_subgraphs", "aggregator")
        builder.add_edge("aggregator", END)

        # 编译
        return builder.compile()

    async def chat(self, message: str) -> AgentResponse:
        """与协调器对话

        Args:
            message: 用户消息

        Returns:
            AgentResponse
        """
        # 确保初始化
        await self._ensure_initialized()

        # 重置追踪
        self._tool_calls = []
        self._sources = []

        start_time = time.time()

        # 发送思考开始事件
        await self._callback.on_event(thinking_event(start=True))

        try:
            # 构建初始状态
            initial_state: OrchestratorState = {
                "messages": [],
                "query": message,
                "reg_id": self.reg_id,
                "intent": None,
                "selected_subgraphs": [],
                "subgraph_results": {},
                "final_content": "",
                "all_sources": [],
                "all_tool_calls": [],
            }

            # 执行父图
            result_state = await self._orchestrator_graph.ainvoke(initial_state)

            # 提取结果
            final_content = result_state.get("final_content", "")
            self._sources = result_state.get("all_sources", [])
            self._tool_calls = result_state.get("all_tool_calls", [])

            # 发送文本事件
            if final_content:
                await self._callback.on_event(text_delta_event(final_content))

            # 发送思考结束事件
            await self._callback.on_event(thinking_event(start=False))

            # 计算耗时
            end_time = time.time()
            duration_ms = (end_time - start_time) * 1000

            # 发送完成事件
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
            logger.exception(f"Orchestrator execution error: {e}")

            await self._callback.on_event(thinking_event(start=False))

            return AgentResponse(
                content=f"查询失败: {str(e)}",
                sources=list(set(self._sources)),
                tool_calls=self._tool_calls,
            )

    async def reset(self) -> None:
        """重置会话状态"""
        self._thread_id = self._generate_thread_id()
        self._tool_calls = []
        self._sources = []

        # 重置所有 SubgraphBuilder
        for builder in self._subgraph_builders.values():
            builder.reset_tracking()

        logger.debug(f"Session reset, new thread_id: {self._thread_id}")

    async def close(self) -> None:
        """关闭连接"""
        if self._mcp_client:
            await self._mcp_client.disconnect()
            self._mcp_client = None
            self._subgraph_builders = {}
            self._orchestrator_graph = None
            logger.debug("MCP client disconnected")

        if hasattr(self, "_ollama_http_client") and self._ollama_http_client:
            await self._ollama_http_client.aclose()
            self._ollama_http_client = None

    async def __aenter__(self) -> "LangGraphOrchestrator":
        """异步上下文管理器入口"""
        await self._ensure_initialized()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        await self.close()
