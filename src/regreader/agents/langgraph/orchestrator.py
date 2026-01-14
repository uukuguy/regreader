"""LangGraph Orchestrator 实现

使用 LangGraph 原生的父图-子图模式实现 LLM 自主选择子智能体。

架构:
    LangGraphOrchestrator
        ├── Main Graph (父图)
        │   ├── router_node (LLM 路由节点) - LLM 根据子图描述自主选择
        │   ├── execute_subgraphs_node - 执行选中的子图
        │   └── aggregator_node - 聚合结果
        └── Subgraphs (子图，通过条件边路由)
            ├── SearchSubgraph
            ├── TableSubgraph
            ├── ReferenceSubgraph
            └── DiscoverySubgraph

关键变更:
- 移除 QueryAnalyzer.analyze()（硬编码路由）
- 使用 QueryAnalyzer.extract_hints() 提取提示信息
- router_node 使用 LLM 根据子图描述自主选择
- LLM 分析查询并返回子图名称列表
"""

import asyncio
import json
import time
import uuid
from typing import TYPE_CHECKING, Annotated, Any, TypedDict

import httpx
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
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
from regreader.orchestrator.analyzer import QueryAnalyzer
from regreader.orchestrator.coordinator import Coordinator
from regreader.orchestrator.result import SubagentResult
from regreader.subagents.config import (
    DISCOVERY_AGENT_CONFIG,
    REFERENCE_AGENT_CONFIG,
    SEARCH_AGENT_CONFIG,
    SUBAGENT_CONFIGS,
    TABLE_AGENT_CONFIG,
    SubagentType,
)
from regreader.subagents.prompts import inject_prompt_to_config

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

    hints: dict[str, Any]
    """查询提示信息"""

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

    使用 LangGraph 原生父图-子图模式实现 LLM 自主选择子智能体。

    工作流程:
    1. QueryAnalyzer 提取查询提示（hints）
    2. router_node: LLM 根据子图描述自主选择要执行的子图
    3. execute_subgraphs_node: 执行选中的子图（顺序或并行）
    4. aggregator_node: 聚合所有子图结果

    特性:
    - LLM 自主决策：根据 SubagentConfig.description 选择子图
    - 原生子图组合：子图作为父图节点，通过 invoke() 调用
    - 状态隔离：父图状态和子图状态分离
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
        coordinator: "Coordinator | None" = None,
    ):
        """初始化 LangGraph 协调器

        Args:
            reg_id: 默认规程标识
            model: LLM 模型名称
            mcp_config: MCP 连接配置
            status_callback: 状态回调
            mode: 执行模式（"sequential" 或 "parallel"）
            enabled_subagents: 启用的 Subagent 列表
            coordinator: 协调器实例（可选，用于文件系统追踪）
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

        # 查询分析器（仅提取 hints）
        self._analyzer = QueryAnalyzer()
        self._aggregator = ResultAggregator()

        # 协调器（可选）
        self._coordinator = coordinator

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

    def _build_router_prompt(self) -> str:
        """构建路由提示词，包含所有子图描述

        Returns:
            路由提示词
        """
        # 收集所有启用的子图描述
        subgraph_descriptions = []
        for agent_type in self._subagraph_builders.keys():
            config = SUBAGENT_CONFIGS.get(agent_type)
            if config and config.enabled:
                subgraph_descriptions.append(f"""
### {agent_type.value} - {config.name}
{config.description}
""")

        descriptions_text = "".join(subgraph_descriptions)

        prompt = f"""分析用户查询，选择合适的子图（可多选）：

# 可用的子图

{descriptions_text}

# 决策指南

- 如果查询涉及**搜索关键词、浏览目录、读取章节**，选择 search
- 如果查询涉及**表格查询、表格提取、注释查找**，选择 table
- 如果查询涉及**交叉引用、"见第X章"、"参见表X"**，选择 reference
- 如果查询涉及**语义分析、相似内容、章节对比**，选择 discovery（如果启用）

# 输出格式

返回 JSON 数组，包含选中的子图名称。例如：
["search", "table"] 或 ["reference"] 或 ["search"]

只返回 JSON 数组，不要其他内容。"""

        return prompt

    def _build_orchestrator_graph(self) -> Any:
        """构建 Orchestrator 父图

        父图结构:
            START -> router -> execute_subgraphs -> aggregator -> END
        """
        # ====================================================================
        # 定义节点函数
        # ====================================================================

        async def router_node(state: OrchestratorState) -> dict:
            """路由节点：LLM 分析查询并选择子图"""
            query = state["query"]

            # 构建路由提示词
            router_prompt = self._build_router_prompt()

            # 调用 LLM 进行路由决策
            messages = [
                SystemMessage(content=router_prompt),
                HumanMessage(content=query),
            ]

            response = await self._llm.ainvoke(messages)
            content = response.content

            # 解析 LLM 输出
            selected = self._parse_router_response(content)

            logger.debug(f"Router selected subgraphs: {selected}")

            return {
                "selected_subgraphs": selected,
            }

        async def execute_subgraphs_node(state: OrchestratorState) -> dict:
            """执行子图节点

            根据 mode 配置决定顺序或并行执行。
            """
            selected = state["selected_subgraphs"]
            query = state["query"]
            reg_id = state["reg_id"]
            hints = state.get("hints", {})

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
            """聚合节点：合并所有子图结果"""
            results = state["subgraph_results"]

            # 转换为 SubagentResult 列表
            subagent_results = []
            for type_value, output in results.items():
                if output["success"]:
                    subagent_results.append(
                        SubagentResult(
                            agent_type=SubagentType(type_value),
                            content=output["content"],
                            sources=output["sources"],
                            tool_calls=output["tool_calls"],
                        )
                    )

            # 聚合结果
            aggregated = self._aggregator.aggregate(subagent_results)

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

        # 编译父图
        return builder.compile()

    def _parse_router_response(self, content: str) -> list[str]:
        """解析 LLM 路由响应

        Args:
            content: LLM 输出内容

        Returns:
            选中的子图名称列表
        """
        try:
            # 尝试直接解析 JSON
            selected = json.loads(content)
            if isinstance(selected, list):
                return selected
        except json.JSONDecodeError:
            pass

        # 尝试提取 JSON 数组
        import re
        match = re.search(r'\[([^\]]+)\]', content)
        if match:
            try:
                selected = json.loads(match.group(0))
                if isinstance(selected, list):
                    return selected
            except json.JSONDecodeError:
                pass

        # 回退：使用 SearchAgent
        logger.warning(f"Failed to parse router response: {content}, falling back to search")
        if SubagentType.SEARCH in self._subgraph_builders:
            return [SubagentType.SEARCH.value]
        
        # 如果 SearchAgent 不可用，返回第一个可用的子图
        if self._subgraph_builders:
            return [list(self._subgraph_builders.keys())[0].value]
        
        return []

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
            # 1. 提取查询提示
            hints = await self._analyzer.extract_hints(message)
            logger.debug(f"Extracted hints: {hints}")

            # 2. 如果使用 Coordinator，记录查询
            if self._coordinator:
                await self._coordinator.log_query(message, hints, self.reg_id)

            # 3. 构建上下文信息（注入到查询中）
            context_info = self._build_context_info(hints)
            enhanced_message = f"{message}\n\n{context_info}" if context_info else message

            # 3. 构建初始状态
            initial_state = OrchestratorState(
                query=enhanced_message,
                reg_id=self.reg_id,
                hints=hints,
                selected_subgraphs=[],
                subgraph_results={},
                final_answer="",
                tool_calls=[],
                sources=[],
            )

            # 4. 执行 Orchestrator Graph
            result = await self._graph.ainvoke(initial_state)

            # 提取结果
            content = result.get("final_answer", "")
            self._tool_calls = result.get("tool_calls", [])
            self._sources = result.get("sources", [])

            # 发送文本事件
            if content:
                await self._callback.on_event(text_delta_event(content))

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

            # 如果使用 Coordinator，写入结果
            if self._coordinator:
                await self._coordinator.write_result(
                    content,
                    list(set(self._sources)),
                    self._tool_calls,
                )

            return AgentResponse(
                content=content,
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

    def _build_context_info(self, hints: dict) -> str:
        """构建上下文信息字符串

        将提取的 hints 和默认 reg_id 格式化为上下文信息。

        Args:
            hints: 提取的提示信息

        Returns:
            上下文信息字符串
        """
        context_parts = []

        # 添加默认规程
        if self.reg_id:
            context_parts.append(f"默认规程: {self.reg_id}")

        # 添加提示信息
        if hints:
            hints_lines = [f"- {k}: {v}" for k, v in hints.items()]
            context_parts.append("查询提示:\n" + "\n".join(hints_lines))

        return "\n\n".join(context_parts) if context_parts else ""

    async def reset(self) -> None:
        """重置会话状态"""
        self._tool_calls = []
        self._sources = []

        logger.debug("Session reset")

    async def close(self) -> None:
        """关闭连接"""
        self._graph = None
        self._subgraph_builders = {}
        self._initialized = False

        logger.debug("Orchestrator closed")

    async def __aenter__(self) -> "LangGraphOrchestrator":
        """异步上下文管理器入口"""
        await self._ensure_initialized()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        await self.close()
