"""Pydantic AI Orchestrator 实现（基于新架构）

使用 OrchestratorAgent 基类和 Pydantic AI 实现 L2 编排智能体。

架构:
    PydanticOrchestrator (继承 OrchestratorAgent)
        ├── 使用 Pydantic AI 作为 LLM 后端
        ├── 集成 HierarchyManager 进行 agent 调度
        ├── 支持 L1 原子化子任务调用
        └── 实现智能结果聚合

关键变更（新架构）:
- 继承 OrchestratorAgent 而非 BaseOrchestrator
- 使用 HierarchyManager 进行 agent 栈管理
- 支持 L1 原子化子任务（locate_chapters, fetch_content, etc.）
- 移除旧的 SEARCH/TABLE/REFERENCE/DISCOVERY 子智能体
"""

from typing import Any

from loguru import logger

from regreader.agents.orchestrator_agent import OrchestratorAgent
from regreader.agents.shared.callbacks import NullCallback, StatusCallback
from regreader.agents.shared.mcp_connection import MCPConnectionConfig, get_mcp_manager
from regreader.core.config import get_settings

# Pydantic AI imports
try:
    from pydantic_ai import Agent
    from pydantic_ai.mcp import MCPServerStdio

    HAS_PYDANTIC_AI = True
except ImportError:
    HAS_PYDANTIC_AI = False
    Agent = None  # type: ignore
    MCPServerStdio = None  # type: ignore


class PydanticOrchestrator(OrchestratorAgent):
    """Pydantic AI 实现的 L2 编排智能体

    使用 Pydantic AI 作为 LLM 后端，实现规划推理和结果聚合。

    特性:
    - 继承 OrchestratorAgent 的核心编排逻辑
    - 使用 Pydantic AI 进行 LLM 调用
    - 集成 MCP 工具访问
    - 集成 HierarchyManager 进行 agent 栈管理

    Usage:
        async with PydanticOrchestrator(reg_id="angui_2024") as agent:
            response = await agent.chat("母线失压如何处理？")
            print(response.content)
    """

    def __init__(
        self,
        reg_id: str | None = None,
        model: str | None = None,
        mcp_config: MCPConnectionConfig | None = None,
        status_callback: StatusCallback | None = None,
        use_coordinator: bool = False,
        session_id: str | None = None,
        parallel_mode: bool = False,
    ):
        """初始化 Pydantic Orchestrator

        Args:
            reg_id: 默认规程ID
            model: LLM 模型名称
            mcp_config: MCP 连接配置
            status_callback: 状态回调
            use_coordinator: 是否使用 Coordinator（Bash+FS 模式）
            session_id: 会话ID
            parallel_mode: 是否启用并行执行模式
        """
        # 调用父类构造函数
        super().__init__(
            reg_id=reg_id,
            use_coordinator=use_coordinator,
            callback=status_callback or NullCallback(),
            session_id=session_id,
            parallel_mode=parallel_mode,
        )

        if not HAS_PYDANTIC_AI:
            raise ImportError(
                "Pydantic AI not installed. Please run: pip install pydantic-ai"
            )

        settings = get_settings()

        # Pydantic AI 使用通用 LLM 配置
        self._model = model or settings.llm_model_name or ""

        # MCP 连接管理器
        self._mcp_manager = get_mcp_manager(mcp_config)

        # Pydantic AI agent (延迟初始化)
        self._agent: Agent | None = None

        logger.info(
            f"PydanticOrchestrator initialized: model={self._model}, "
            f"session_id={session_id or 'auto'}"
        )

    @property
    def name(self) -> str:
        """Agent 名称"""
        return "PydanticOrchestrator"

    @property
    def model(self) -> str:
        """模型名称"""
        return self._model

    async def _ensure_initialized(self) -> None:
        """初始化 Pydantic AI agent 和 MCP 连接

        扩展父类的初始化，添加 Pydantic AI 特定的初始化。
        """
        # 调用父类初始化（注册到 HierarchyManager）
        await super()._ensure_initialized()

        if self._agent is None:
            # 初始化 MCP 连接
            if not self._mcp_manager.is_connected():
                await self._mcp_manager.connect()
                logger.info("MCP manager connected")

            # 创建 Pydantic AI agent
            try:
                self._agent = Agent(
                    model=self._model,
                    system_prompt="You are an orchestrator agent for regulation retrieval.",
                )
                logger.info("Pydantic AI agent initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Pydantic AI agent: {e}")
                raise

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self._ensure_initialized()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        # 清理 MCP 连接
        if self._mcp_manager and self._mcp_manager.is_connected():
            await self._mcp_manager.disconnect()
            logger.info("MCP manager disconnected")
