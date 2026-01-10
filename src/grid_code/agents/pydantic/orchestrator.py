"""Pydantic AI Orchestrator 实现

协调多个 Pydantic Subagent 的执行，实现查询路由和结果聚合。

架构:
    PydanticOrchestrator
        ├── QueryAnalyzer (查询意图分析)
        ├── SubagentRouter (路由调度)
        ├── Subagents (专家代理)
        │   ├── SearchSubagent
        │   ├── TableSubagent
        │   ├── ReferenceSubagent
        │   └── DiscoverySubagent
        └── ResultAggregator (结果聚合)
"""

import os
import time
from typing import TYPE_CHECKING

from loguru import logger

from grid_code.agents.base import AgentResponse, BaseGridCodeAgent
from grid_code.agents.callbacks import NullCallback, StatusCallback
from grid_code.agents.events import (
    response_complete_event,
    text_delta_event,
    thinking_event,
)
from grid_code.agents.mcp_connection import MCPConnectionConfig, get_mcp_manager
from grid_code.agents.pydantic.subagents import create_pydantic_subagent
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

# Pydantic AI imports
try:
    from pydantic_ai.mcp import MCPServerStdio

    HAS_PYDANTIC_AI = True
except ImportError:
    HAS_PYDANTIC_AI = False
    MCPServerStdio = None  # type: ignore

if TYPE_CHECKING:
    pass


class PydanticOrchestrator(BaseGridCodeAgent):
    """Pydantic AI 协调器

    使用 Dependent Agents 模式协调多个专家代理。

    工作流程:
    1. QueryAnalyzer 分析查询意图
    2. SubagentRouter 选择需要调用的 Subagent
    3. 执行 Subagents（顺序或并行）
    4. ResultAggregator 聚合结果

    特性:
    - 上下文隔离：每个 Subagent 持有独立的过滤工具集
    - 灵活路由：基于关键词和意图分析选择 Subagent
    - 结果聚合：合并多个 Subagent 的结果

    Usage:
        async with PydanticOrchestrator(reg_id="angui_2024") as agent:
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
        """初始化 Pydantic AI 协调器

        Args:
            reg_id: 默认规程标识
            model: LLM 模型名称
            mcp_config: MCP 连接配置
            status_callback: 状态回调
            mode: 执行模式（"sequential" 或 "parallel"）
            enabled_subagents: 启用的 Subagent 列表
        """
        super().__init__(reg_id)

        if not HAS_PYDANTIC_AI:
            raise ImportError(
                "Pydantic AI not installed. Please run: pip install 'pydantic-ai>=1.0.0'"
            )

        settings = get_settings()
        self._model_name = model or settings.llm_model_name
        self._is_ollama = settings.is_ollama_backend()
        self._mode = mode

        # 确定启用的 Subagent
        if enabled_subagents is None:
            enabled_subagents = ["search", "table", "reference"]
        self._enabled_subagents = set(enabled_subagents)

        # 状态回调
        self._callback = status_callback or NullCallback()

        # 设置环境变量
        os.environ["OPENAI_API_KEY"] = settings.llm_api_key
        os.environ["OPENAI_BASE_URL"] = settings.llm_base_url

        # 构建模型标识
        if self._is_ollama:
            # Ollama 使用 openai: 前缀
            ollama_base = settings.llm_base_url
            if not ollama_base.endswith("/v1"):
                ollama_base = ollama_base.rstrip("/") + "/v1"
            os.environ["OPENAI_BASE_URL"] = ollama_base
            self._model = f"openai:{self._model_name}"
        else:
            self._model = f"openai:{self._model_name}"

        # MCP 连接管理器
        self._mcp_manager = get_mcp_manager(mcp_config)

        # MCP Server（延迟初始化）
        self._mcp_server: MCPServerStdio | None = None

        # Subagents（延迟初始化）
        self._subagents: dict[SubagentType, BaseSubagent] = {}

        # 协调组件
        self._analyzer = QueryAnalyzer()
        self._router: SubagentRouter | None = None
        self._aggregator = ResultAggregator()

        # 工具调用追踪
        self._tool_calls: list[dict] = []
        self._sources: list[str] = []

        # 连接状态
        self._connected = False

        logger.info(
            f"PydanticOrchestrator initialized: model={self._model}, "
            f"mode={self._mode}, enabled_subagents={self._enabled_subagents}"
        )

    @property
    def name(self) -> str:
        return "PydanticOrchestrator"

    @property
    def model(self) -> str:
        return self._model

    async def _ensure_initialized(self) -> None:
        """确保组件已初始化"""
        if not self._connected:
            # 获取 MCP Server
            self._mcp_server = self._mcp_manager.get_pydantic_mcp_server()

            # 创建 Subagents
            self._subagents = await self._create_subagents()

            # 创建路由器
            self._router = SubagentRouter(self._subagents, mode=self._mode)

            self._connected = True

            logger.debug(
                f"Orchestrator initialized with subagents: "
                f"{list(self._subagents.keys())}"
            )

    async def _create_subagents(self) -> dict[SubagentType, BaseSubagent]:
        """创建 Subagent 实例"""
        subagents = {}

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

            # 创建 Subagent
            subagent = create_pydantic_subagent(
                config, self._model, self._mcp_server
            )
            subagents[agent_type] = subagent

        return subagents

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
        self._tool_calls = []
        self._sources = []

        # 重置所有 Subagent
        for subagent in self._subagents.values():
            await subagent.reset()

        logger.debug("Session reset")

    async def close(self) -> None:
        """关闭连接"""
        # 关闭所有 Subagent
        for subagent in self._subagents.values():
            if hasattr(subagent, "close"):
                await subagent.close()

        self._subagents = {}
        self._router = None
        self._connected = False

        logger.debug("Orchestrator closed")

    async def __aenter__(self) -> "PydanticOrchestrator":
        """异步上下文管理器入口"""
        await self._ensure_initialized()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        await self.close()
