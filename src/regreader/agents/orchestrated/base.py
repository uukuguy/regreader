"""Orchestrator 抽象基类

提供三个框架共享的基础设施，消除代码重复。
"""

import json
from abc import ABC, abstractmethod
from typing import Any

from loguru import logger

from regreader.agents.base import AgentResponse, BaseRegReaderAgent
from regreader.agents.shared.callbacks import NullCallback, StatusCallback
from regreader.agents.shared.events import (
    AgentEvent,
    response_complete_event,
    thinking_event,
)
from regreader.orchestration.analyzer import QueryAnalyzer
from regreader.orchestration.coordinator import Coordinator
from regreader.subagents.config import SubagentConfig


class BaseOrchestrator(BaseRegReaderAgent, ABC):
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
        reg_id: str | None = None,
        use_coordinator: bool = False,
        callback: StatusCallback | None = None,
    ):
        """初始化 Orchestrator

        Args:
            reg_id: 默认规程ID
            use_coordinator: 是否使用 Coordinator（Bash+FS 模式）
            callback: 状态回调
        """
        super().__init__(reg_id)
        self.use_coordinator = use_coordinator
        self.callback = callback or NullCallback()
        self._initialized = False
        self._sources: list[str] = []
        self._tool_calls: list[dict] = []

        # Coordinator（如果启用）
        self.coordinator: Coordinator | None = None
        if use_coordinator:
            self.coordinator = Coordinator()

    # === 共享方法（具体实现） ===

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

    def _extract_sources(self, result: Any) -> None:
        """递归提取来源引用

        从工具调用结果中提取所有 source 字段。

        Args:
            result: 工具调用结果（可能是 dict, list, str）
        """
        if isinstance(result, dict):
            # 提取 source 字段
            if "source" in result:
                source = result["source"]
                if source and source not in self._sources:
                    self._sources.append(source)

            # 递归处理所有值
            for value in result.values():
                self._extract_sources(value)

        elif isinstance(result, list):
            # 递归处理列表元素
            for item in result:
                self._extract_sources(item)

        elif isinstance(result, str):
            # 尝试解析 JSON 字符串
            try:
                parsed = json.loads(result)
                self._extract_sources(parsed)
            except (json.JSONDecodeError, TypeError):
                pass

    def _reset_tracking(self) -> None:
        """重置跟踪状态

        清空 sources 和 tool_calls 列表，准备新的查询。
        """
        self._sources.clear()
        self._tool_calls.clear()

    async def _send_event(self, event: AgentEvent) -> None:
        """发送事件到回调

        Args:
            event: Agent 事件
        """
        await self.callback.on_event(event)

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

    async def chat(self, message: str) -> AgentResponse:
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

        Returns:
            AgentResponse 包含回答内容和来源引用
        """
        # 1. 确保初始化
        await self._ensure_initialized()

        # 2. 重置跟踪
        self._reset_tracking()

        # 3. 提取提示
        hints = QueryAnalyzer.extract_hints(message)
        logger.debug(f"Extracted hints: {hints}")

        # 4. 记录查询（如果使用 Coordinator）
        if self.use_coordinator and self.coordinator:
            self.coordinator.log_query(message)

        # 5. 构建上下文
        context_info = self._build_context_info(hints)
        if context_info:
            logger.debug(f"Context info: {context_info}")

        # 6. 发送思考事件
        await self._send_event(thinking_event("正在分析查询..."))

        # 7. 执行编排（框架特定）
        try:
            content = await self._execute_orchestration(message, context_info)
        except Exception as e:
            logger.error(f"Orchestration failed: {e}")
            raise

        # 8. 发送完成事件
        await self._send_event(response_complete_event())

        # 9. 写入结果（如果使用 Coordinator）
        if self.use_coordinator and self.coordinator:
            self.coordinator.write_result(content, self._sources)

        # 10. 返回响应
        return AgentResponse(
            content=content,
            sources=self._sources,
            tool_calls=self._tool_calls,
        )

    async def reset(self):
        """重置对话历史

        子类可以重写此方法来重置框架特定的状态。
        """
        self._reset_tracking()
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
