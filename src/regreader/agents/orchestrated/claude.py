"""Claude SDK Orchestrator 实现（基于新架构）

使用 OrchestratorAgent 基类和 Claude SDK 实现 L2 编排智能体。

架构:
    ClaudeOrchestrator (继承 OrchestratorAgent)
        ├── 使用 Claude SDK 作为 LLM 后端
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

# Claude Agent SDK imports
try:
    from claude_agent_sdk import (
        ClaudeAgentOptions,
        ClaudeSDKClient,
        ClaudeSDKError,
    )

    HAS_CLAUDE_SDK = True
except ImportError:
    HAS_CLAUDE_SDK = False
    ClaudeAgentOptions = None  # type: ignore
    ClaudeSDKClient = None  # type: ignore
    ClaudeSDKError = Exception  # type: ignore


class ClaudeOrchestrator(OrchestratorAgent):
    """Claude SDK 实现的 L2 编排智能体

    使用 Claude SDK 作为 LLM 后端，实现规划推理和结果聚合。

    特性:
    - 继承 OrchestratorAgent 的核心编排逻辑
    - 使用 Claude SDK 进行 LLM 调用
    - 集成 MCP 工具访问
    - 支持 preset: "claude_code" (Anthropic 官方最佳实践)
    - 集成 HierarchyManager 进行 agent 栈管理

    Usage:
        async with ClaudeOrchestrator(reg_id="angui_2024") as agent:
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
        use_preset: bool = True,
        parallel_mode: bool = False,
    ):
        """初始化 Claude Orchestrator

        Args:
            reg_id: 默认规程ID
            model: Claude 模型名称
            mcp_config: MCP 连接配置
            status_callback: 状态回调
            use_coordinator: 是否使用 Coordinator（Bash+FS 模式）
            session_id: 会话ID
            use_preset: 是否使用 preset: "claude_code"
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

        if not HAS_CLAUDE_SDK:
            raise ImportError(
                "Claude Agent SDK not installed. Please run: pip install claude-agent-sdk"
            )

        settings = get_settings()

        # Claude 使用 Anthropic 专用配置，如果未设置则回退到通用 LLM 配置
        self._model = model or settings.anthropic_model_name or settings.llm_model_name
        self._use_preset = use_preset

        # MCP 连接管理器
        self._mcp_manager = get_mcp_manager(mcp_config)

        # Claude SDK client (延迟初始化)
        self._client: ClaudeSDKClient | None = None

        logger.info(
            f"ClaudeOrchestrator initialized: model={self._model}, "
            f"use_preset={self._use_preset}, "
            f"session_id={session_id or 'auto'}"
        )

    @property
    def name(self) -> str:
        """Agent 名称"""
        return "ClaudeOrchestrator"

    @property
    def model(self) -> str:
        """模型名称"""
        return self._model

    async def _ensure_initialized(self) -> None:
        """初始化 Claude SDK client 和 MCP 连接

        扩展父类的初始化，添加 Claude SDK 特定的初始化。
        """
        # 调用父类初始化（注册到 HierarchyManager）
        await super()._ensure_initialized()

        if self._client is None:
            # 初始化 MCP 连接
            if not self._mcp_manager.is_connected():
                await self._mcp_manager.connect()
                logger.info("MCP manager connected")

            # 创建 Claude SDK client
            try:
                # 设置环境变量（Claude SDK 从环境变量读取 API 配置）
                import os
                settings = get_settings()

                # 优先使用 Anthropic 专用配置，如果未设置则回退到通用 LLM 配置
                api_key = settings.anthropic_api_key or settings.llm_api_key
                base_url = settings.anthropic_base_url or settings.llm_base_url

                if api_key:
                    os.environ["ANTHROPIC_API_KEY"] = api_key
                if base_url:
                    os.environ["ANTHROPIC_BASE_URL"] = base_url

                logger.debug(
                    f"Claude SDK configuration: "
                    f"api_key={'***' if api_key else 'NOT SET'}, "
                    f"base_url={base_url}"
                )

                # 创建 ClaudeAgentOptions（不需要 api_key 和 base_url 参数）
                options = ClaudeAgentOptions(
                    mcp_servers=self._mcp_manager.get_claude_sdk_config(),
                    permission_mode="bypassPermissions",
                    max_turns=10,
                )

                self._client = ClaudeSDKClient(options=options)
                logger.info("Claude SDK client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Claude SDK client: {e}")
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
