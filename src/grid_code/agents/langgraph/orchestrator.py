"""LangGraph Orchestrator 实现

协调多个 Subgraph 的执行，实现查询路由和结果聚合。

架构:
    LangGraphOrchestrator
        ├── QueryAnalyzer (查询意图分析)
        ├── SubagentRouter (路由调度)
        ├── Subgraphs (专家代理)
        │   ├── SearchSubgraph
        │   ├── TableSubgraph
        │   ├── ReferenceSubgraph
        │   └── DiscoverySubgraph
        └── ResultAggregator (结果聚合)
"""

import time
import uuid
from typing import TYPE_CHECKING

import httpx
from langchain_openai import ChatOpenAI
from loguru import logger

from grid_code.agents.base import AgentResponse, BaseGridCodeAgent
from grid_code.agents.callbacks import NullCallback, StatusCallback
from grid_code.agents.events import (
    response_complete_event,
    text_delta_event,
    thinking_event,
)
from grid_code.agents.langgraph.subgraphs import SUBGRAPH_CLASSES, create_subgraph
from grid_code.agents.llm_timing import LLMTimingCollector
from grid_code.agents.mcp_connection import MCPConnectionConfig, get_mcp_manager
from grid_code.config import get_settings
from grid_code.orchestrator.aggregator import ResultAggregator
from grid_code.orchestrator.analyzer import QueryAnalyzer
from grid_code.orchestrator.router import SubagentRouter
from grid_code.subagents.base import BaseSubagent, SubagentContext
from grid_code.subagents.config import (
    DISCOVERY_AGENT_CONFIG,
    REFERENCE_AGENT_CONFIG,
    SEARCH_AGENT_CONFIG,
    TABLE_AGENT_CONFIG,
    SubagentType,
)
from grid_code.subagents.prompts import inject_prompt_to_config

# 在模块加载时注入提示词到配置
inject_prompt_to_config()

if TYPE_CHECKING:
    from grid_code.mcp import GridCodeMCPClient


class LangGraphOrchestrator(BaseGridCodeAgent):
    """LangGraph 协调器

    使用 Subgraph 模式协调多个专家代理。

    工作流程:
    1. QueryAnalyzer 分析查询意图
    2. SubagentRouter 选择需要调用的 Subgraph
    3. 执行 Subgraphs（顺序或并行）
    4. ResultAggregator 聚合结果

    特性:
    - 上下文隔离：每个 Subgraph 持有独立的工具和提示词
    - 灵活路由：基于关键词和意图分析选择 Subgraph
    - 结果聚合：合并多个 Subgraph 的结果

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
        self._mcp_client: GridCodeMCPClient | None = None

        # Subgraphs（延迟初始化）
        self._subgraphs: dict[SubagentType, BaseSubagent] = {}

        # 协调组件
        self._analyzer = QueryAnalyzer()
        self._router: SubagentRouter | None = None
        self._aggregator = ResultAggregator()

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

            # 创建 Subgraphs
            self._subgraphs = self._create_subgraphs()

            # 创建路由器
            self._router = SubagentRouter(self._subgraphs, mode=self._mode)

            logger.debug(
                f"Orchestrator initialized with subgraphs: "
                f"{list(self._subgraphs.keys())}"
            )

    def _create_subgraphs(self) -> dict[SubagentType, BaseSubagent]:
        """创建 Subgraph 实例"""
        subgraphs = {}

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

            # 创建 Subgraph
            subgraph = create_subgraph(config, self._llm, self._mcp_client)
            subgraphs[agent_type] = subgraph

        return subgraphs

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
            # 1. 分析查询意图
            intent = await self._analyzer.analyze(message)
            logger.debug(
                f"Query intent: primary={intent.primary_type}, "
                f"secondary={intent.secondary_types}, "
                f"multi_hop={intent.requires_multi_hop}"
            )

            # 2. 构建上下文
            context = SubagentContext(
                query=message,
                reg_id=self.reg_id,
                chapter_scope=intent.hints.get("chapter_scope"),
                hints=intent.hints,
                max_iterations=5,
            )

            # 3. 路由和执行
            results = await self._router.execute(intent, context)

            # 4. 聚合结果
            aggregated = self._aggregator.aggregate(results, message)

            # 收集所有工具调用和来源
            for result in results:
                self._tool_calls.extend(result.tool_calls)
                self._sources.extend(result.sources)

            # 发送文本事件
            if aggregated.content:
                await self._callback.on_event(text_delta_event(aggregated.content))

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

            return self._aggregator.to_agent_response(aggregated)

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

        # 重置所有 Subgraph
        for subgraph in self._subgraphs.values():
            await subgraph.reset()

        logger.debug(f"Session reset, new thread_id: {self._thread_id}")

    async def close(self) -> None:
        """关闭连接"""
        if self._mcp_client:
            await self._mcp_client.disconnect()
            self._mcp_client = None
            self._subgraphs = {}
            self._router = None
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
