"""Orchestrator 抽象基类

基于 agentex 框架的 Orchestrator 基类，提供 L2 编排智能体的共享基础设施。
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from loguru import logger

from ...agents.shared.callbacks import NullCallback, StatusCallback
from ...orchestration.analyzer import QueryAnalyzer
from ...orchestration.coordinator import Coordinator
from ..base import AgentResponse, RegReaderAgent
from ..config import OrchestratorConfig, RegReaderConfig
from ..events import EventAdapter


class BaseOrchestrator(RegReaderAgent, ABC):
    """Orchestrator 抽象基类

    提供三个框架（Claude SDK, Pydantic AI, LangGraph）共享的基础设施：
    - 上下文构建
    - 来源提取
    - 事件处理
    - 生命周期管理

    子类只需实现两个抽象方法：
    - _ensure_initialized(): 初始化框架特定组件
    - _execute_orchestration(): 执行框架特定的编排逻辑
    """

    def __init__(
        self,
        config: OrchestratorConfig | RegReaderConfig | None = None,
        reg_id: str | None = None,
        use_coordinator: bool = False,
        status_callback: StatusCallback | None = None,
        parallel_mode: bool = False,
    ):
        """初始化 Orchestrator

        Args:
            config: Orchestrator 配置
            reg_id: 默认规程ID
            use_coordinator: 是否使用 Coordinator（Bash+FS 模式）
            status_callback: 状态回调
            parallel_mode: 是否启用并行执行模式
        """
        # 构建配置
        if config is None:
            config = OrchestratorConfig()

        # 如果传入的是 RegReaderConfig，转换为 OrchestratorConfig
        if not isinstance(config, OrchestratorConfig):
            config = OrchestratorConfig(
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
                use_coordinator=use_coordinator,
                parallel_mode=parallel_mode,
            )

        super().__init__(config=config, reg_id=reg_id, status_callback=status_callback)

        self.use_coordinator = use_coordinator
        self.parallel_mode = parallel_mode
        self._initialized = False
        self._sources: list[str] = []
        self._tool_calls: list[dict] = []

        # QueryAnalyzer（用于提取查询提示）
        self._analyzer = QueryAnalyzer()

        # Coordinator（如果启用）
        self.coordinator: Coordinator | None = None
        if use_coordinator:
            self.coordinator = Coordinator()

    # === 共享方法（具体实现） ===

    async def _create_agent(self) -> Any:
        """创建底层 Agent（Orchestrator 不使用此方法）

        Orchestrator 使用 _ensure_initialized 和 _execute_orchestration 模式，
        而不是 _create_agent 模式。此方法提供一个空实现以满足抽象基类要求。

        Returns:
            None（Orchestrator 不创建 agentex Agent）
        """
        # Orchestrator 不使用 agentex Agent，而是直接使用框架特定的 LLM 客户端
        return None

    def _build_context_info(self, hints: dict[str, Any]) -> str:
        """构建上下文信息

        将 reg_id 和 hints 格式化为上下文字符串。

        Args:
            hints: QueryAnalyzer 提取的提示信息

        Returns:
            格式化的上下文字符串
        """
        context_parts = []

        if self.reg_id:
            context_parts.append(f"默认规程: {self.reg_id}")

        if hints:
            hints_lines = [f"- {k}: {v}" for k, v in hints.items() if v]
            if hints_lines:
                context_parts.append("查询提示:\n" + "\n".join(hints_lines))

        return "\n\n".join(context_parts) if context_parts else ""

    def _extract_sources_from_result(self, result: Any) -> None:
        """递归提取来源引用

        从工具调用结果中提取所有 source 字段。

        Args:
            result: 工具调用结果（可能是 dict, list, str）
        """
        if isinstance(result, dict):
            if "source" in result:
                source = result["source"]
                if source and source not in self._sources:
                    self._sources.append(source)

            for value in result.values():
                self._extract_sources_from_result(value)

        elif isinstance(result, list):
            for item in result:
                self._extract_sources_from_result(item)

        elif isinstance(result, str):
            try:
                parsed = json.loads(result)
                self._extract_sources_from_result(parsed)
            except (json.JSONDecodeError, TypeError):
                pass

    def _reset_tracking(self) -> None:
        """重置跟踪状态

        清空 sources 和 tool_calls 列表，准备新的查询。
        """
        self._sources.clear()
        self._tool_calls.clear()

    # === 抽象方法（子类实现） ===

    @abstractmethod
    async def _ensure_initialized(self) -> None:
        """初始化组件（框架特定）

        子类需要实现此方法来初始化框架特定的组件：
        - Claude SDK: 创建 Agent 和 Subagent 定义
        - Pydantic AI: 创建 Agent 并注册工具
        - LangGraph: 构建 Graph 和 Subgraph

        此方法应该是幂等的（多次调用无副作用）。
        """
        pass

    @abstractmethod
    async def _execute_orchestration(
        self,
        query: str,
        context_info: str,
    ) -> str:
        """执行编排逻辑（框架特定）

        子类需要实现此方法来执行框架特定的编排逻辑：
        - Claude SDK: 使用 Handoff Pattern
        - Pydantic AI: 使用 Delegation Pattern
        - LangGraph: 使用 Subgraph Pattern

        Args:
            query: 用户查询
            context_info: 上下文信息（由 _build_context_info 生成）

        Returns:
            最终回答内容

        Raises:
            任何执行过程中的异常
        """
        pass

    # === 模板方法（统一流程） ===

    async def chat(
        self,
        message: str,
        session_id: str | None = None,
    ) -> AgentResponse:
        """统一的 chat 流程（模板方法）

        定义了所有 Orchestrator 的标准执行流程：
        1. 确保初始化
        2. 重置跟踪
        3. 提取提示
        4. 记录查询（如果使用 Coordinator）
        5. 构建上下文
        6. 发送思考事件
        7. 执行编排（框架特定）
        8. 发送完成事件
        9. 写入结果（如果使用 Coordinator）
        10. 返回响应

        Args:
            message: 用户消息
            session_id: 会话ID（可选）

        Returns:
            AgentResponse 包含回答内容和来源引用
        """
        # 获取或创建会话
        session = self._session_manager.get_or_create(session_id)
        session.reset_per_query()

        # 1. 确保初始化
        await self._ensure_initialized()

        # 2. 重置跟踪
        self._reset_tracking()

        # 3. 提取提示
        hints = self._analyzer.extract_hints_sync(message)
        logger.debug(f"Extracted hints: {hints}")

        # 4. 记录查询（如果使用 Coordinator）
        if self.use_coordinator and self.coordinator:
            await self.coordinator.log_query(message, hints, self.reg_id)

        # 5. 构建上下文
        context_info = self._build_context_info(hints)
        if context_info:
            logger.debug(f"Context info: {context_info}")

        # 6. 发送思考事件
        await self._callback.on_event(EventAdapter.create_thinking_event(start=True))

        # 7. 执行编排（框架特定）
        try:
            content = await self._execute_orchestration(message, context_info)
        except Exception as e:
            logger.error(f"Orchestration failed: {e}")
            await self._callback.on_event(EventAdapter.create_thinking_event(start=False))
            raise

        # 8. 发送完成事件
        await self._callback.on_event(EventAdapter.create_thinking_event(start=False))
        await self._callback.on_event(
            EventAdapter.create_response_complete_event(
                content=content,
                sources=self._sources,
            )
        )

        # 9. 写入结果（如果使用 Coordinator）
        if self.use_coordinator and self.coordinator:
            await self.coordinator.write_result(content, self._sources, self._tool_calls)

        # 10. 同步到会话
        for tc in self._tool_calls:
            session.add_tool_call(
                name=tc.get("name", "unknown"),
                input_data=tc.get("input", {}),
                output=tc.get("output"),
            )
        for source in self._sources:
            session.add_source(source)

        # 11. 返回响应
        return AgentResponse(
            content=content,
            sources=self._sources,
            tool_calls=self._tool_calls,
        )

    async def reset(self, session_id: str | None = None) -> None:
        """重置对话历史

        子类可以重写此方法来重置框架特定的状态。
        """
        self._session_manager.reset(session_id)
        self._reset_tracking()
        if self._memory:
            self._memory.clear_query_context()
        logger.debug(f"{self.name} reset")

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent 名称"""
        pass

    @property
    @abstractmethod
    def model(self) -> str:
        """使用的模型名称"""
        pass

    async def close(self) -> None:
        """关闭 Agent 连接"""
        pass

    async def __aenter__(self) -> "BaseOrchestrator":
        """异步上下文管理器入口"""
        await self._ensure_initialized()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        await self.close()
