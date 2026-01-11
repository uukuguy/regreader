"""Pydantic AI Orchestrator 实现

使用 Pydantic AI 原生的 Agent 委托模式:
- Orchestrator 是主 Agent，通过 @tool 装饰器注册委托工具
- 每个 @tool 内部调用对应的 Subagent
- 使用 deps/usage 传递实现依赖注入和使用量追踪

架构:
    OrchestratorAgent (主协调器 Agent)
        ├── @tool call_search_agent(ctx, query) -> 调用 SearchSubagent
        ├── @tool call_table_agent(ctx, query) -> 调用 TableSubagent
        ├── @tool call_reference_agent(ctx, query) -> 调用 ReferenceSubagent
        └── @tool call_discovery_agent(ctx, query) -> 调用 DiscoverySubagent

    执行流程:
    1. 用户查询 -> OrchestratorAgent
    2. OrchestratorAgent 决定调用哪个 @tool
    3. @tool 内部: result = await subagent.run(query, deps=ctx.deps, usage=ctx.usage)
    4. 返回聚合结果

关键特性:
    - 原生委托模式：Subagent 作为工具被调用
    - 依赖注入：通过 ctx.deps 传递共享依赖
    - 使用量聚合：通过 ctx.usage 追踪所有 token 消耗
"""

import os
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from loguru import logger

from grid_code.agents.base import AgentResponse, BaseGridCodeAgent
from grid_code.agents.callbacks import NullCallback, StatusCallback
from grid_code.agents.events import (
    response_complete_event,
    text_delta_event,
    thinking_event,
)
from grid_code.agents.mcp_connection import MCPConnectionConfig, get_mcp_manager
from grid_code.agents.pydantic.subagents import (
    SubagentBuilder,
    SubagentDependencies,
    SubagentOutput,
    create_subagent_builder,
)
from grid_code.config import get_settings
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
    from pydantic_ai import Agent, RunContext
    from pydantic_ai.mcp import MCPServerStdio
    from pydantic_ai.usage import Usage

    HAS_PYDANTIC_AI = True
except ImportError:
    HAS_PYDANTIC_AI = False
    Agent = None  # type: ignore
    RunContext = None  # type: ignore
    MCPServerStdio = None  # type: ignore
    Usage = None  # type: ignore

if TYPE_CHECKING:
    pass


# ============================================================================
# Orchestrator Dependencies
# ============================================================================


@dataclass
class OrchestratorDependencies:
    """Orchestrator 共享依赖

    通过 ctx.deps 传递给 Orchestrator 和所有 Subagent。

    Attributes:
        reg_id: 规程 ID
        mcp_server: MCP Server
        subagent_builders: Subagent 构建器映射
        subagent_agents: 已构建的 Subagent Agent 映射
        hints: 额外提示信息
    """

    reg_id: str | None = None
    mcp_server: Any = None  # MCPServerStdio
    subagent_builders: dict[SubagentType, SubagentBuilder] = field(default_factory=dict)
    subagent_agents: dict[SubagentType, Any] = field(default_factory=dict)  # Agent instances
    hints: dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Orchestrator System Prompt
# ============================================================================


ORCHESTRATOR_SYSTEM_PROMPT = """你是电力系统安全规程智能问答系统的协调器。

你的职责是：
1. 理解用户的问题意图
2. 选择合适的专家代理来回答问题
3. 综合专家代理的回答，给出最终答案

可用的专家代理：
- call_search_agent: 搜索专家，用于规程发现、目录导航、内容搜索
- call_table_agent: 表格专家，用于表格搜索、跨页合并、注释追踪
- call_reference_agent: 引用专家，用于交叉引用解析、引用内容提取
- call_discovery_agent: 发现专家，用于相似内容发现、章节比较

工作流程：
1. 分析用户问题，确定需要调用哪些专家
2. 调用相应的专家代理工具
3. 根据专家返回的信息，组织最终答案

注意：
- 如果问题涉及表格内容（如"表X-X"），优先使用表格专家
- 如果问题涉及引用（如"见第X章"、"注1"），使用引用专家
- 对于一般搜索问题，使用搜索专家
- 可以同时调用多个专家获取更全面的信息
"""


# ============================================================================
# Orchestrator Agent Factory
# ============================================================================


def create_orchestrator_agent(
    model: str,
    mcp_server: "MCPServerStdio",
    enabled_subagents: set[str],
) -> tuple["Agent[OrchestratorDependencies, str]", dict[SubagentType, SubagentBuilder]]:
    """创建 Orchestrator Agent 和 Subagent Builders

    Args:
        model: LLM 模型标识
        mcp_server: MCP Server
        enabled_subagents: 启用的 Subagent 名称集合

    Returns:
        (Orchestrator Agent, SubagentBuilders 映射)
    """
    # 创建 Subagent Builders
    subagent_builders: dict[SubagentType, SubagentBuilder] = {}

    configs = {
        SubagentType.SEARCH: SEARCH_AGENT_CONFIG,
        SubagentType.TABLE: TABLE_AGENT_CONFIG,
        SubagentType.REFERENCE: REFERENCE_AGENT_CONFIG,
        SubagentType.DISCOVERY: DISCOVERY_AGENT_CONFIG,
    }

    for agent_type, config in configs.items():
        if agent_type.value not in enabled_subagents:
            continue
        if not config.enabled:
            continue

        builder = create_subagent_builder(config, model)
        subagent_builders[agent_type] = builder

    # 创建 Orchestrator Agent
    orchestrator = Agent(
        model,
        deps_type=OrchestratorDependencies,
        system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
    )

    # 注册 Subagent 委托工具
    _register_subagent_tools(orchestrator, subagent_builders)

    return orchestrator, subagent_builders


def _register_subagent_tools(
    orchestrator: "Agent[OrchestratorDependencies, str]",
    subagent_builders: dict[SubagentType, SubagentBuilder],
) -> None:
    """注册 Subagent 委托工具

    使用 @orchestrator.tool 装饰器为每个 Subagent 注册委托工具。
    """

    if SubagentType.SEARCH in subagent_builders:
        @orchestrator.tool
        async def call_search_agent(
            ctx: "RunContext[OrchestratorDependencies]",
            query: str,
        ) -> str:
            """调用搜索专家代理

            用于规程发现、目录导航、内容搜索等任务。

            Args:
                query: 搜索查询内容
            """
            return await _invoke_subagent(ctx, SubagentType.SEARCH, query)

    if SubagentType.TABLE in subagent_builders:
        @orchestrator.tool
        async def call_table_agent(
            ctx: "RunContext[OrchestratorDependencies]",
            query: str,
        ) -> str:
            """调用表格专家代理

            用于表格搜索、跨页合并、注释追踪等任务。

            Args:
                query: 表格相关查询内容
            """
            return await _invoke_subagent(ctx, SubagentType.TABLE, query)

    if SubagentType.REFERENCE in subagent_builders:
        @orchestrator.tool
        async def call_reference_agent(
            ctx: "RunContext[OrchestratorDependencies]",
            query: str,
        ) -> str:
            """调用引用专家代理

            用于交叉引用解析、引用内容提取等任务。

            Args:
                query: 引用相关查询内容
            """
            return await _invoke_subagent(ctx, SubagentType.REFERENCE, query)

    if SubagentType.DISCOVERY in subagent_builders:
        @orchestrator.tool
        async def call_discovery_agent(
            ctx: "RunContext[OrchestratorDependencies]",
            query: str,
        ) -> str:
            """调用发现专家代理

            用于相似内容发现、章节比较等任务。

            Args:
                query: 发现相关查询内容
            """
            return await _invoke_subagent(ctx, SubagentType.DISCOVERY, query)


async def _invoke_subagent(
    ctx: "RunContext[OrchestratorDependencies]",
    agent_type: SubagentType,
    query: str,
) -> str:
    """调用 Subagent 的通用方法

    实现 Pydantic AI 原生的委托模式：
    - 从 ctx.deps 获取共享依赖
    - 传递 ctx.usage 以聚合使用量

    Args:
        ctx: 运行上下文
        agent_type: Subagent 类型
        query: 查询内容

    Returns:
        Subagent 的回答内容
    """
    deps = ctx.deps
    builder = deps.subagent_builders.get(agent_type)

    if builder is None:
        return f"错误: {agent_type.value} 专家代理未启用"

    # 获取或创建 Subagent Agent 实例
    if agent_type not in deps.subagent_agents:
        deps.subagent_agents[agent_type] = builder.build(deps.mcp_server)

    subagent = deps.subagent_agents[agent_type]

    # 创建 Subagent 依赖
    subagent_deps = SubagentDependencies(
        reg_id=deps.reg_id,
        mcp_server=deps.mcp_server,
        hints=deps.hints,
    )

    # 调用 Subagent（传递 usage 以聚合使用量）
    output = await builder.invoke(
        subagent,
        query,
        subagent_deps,
        usage=ctx.usage,  # 关键：传递 usage 以聚合 token 消耗
    )

    if not output.success:
        return f"错误: {output.error}"

    # 返回内容（来源信息已在 output 中追踪）
    return output.content


# ============================================================================
# PydanticOrchestrator Class
# ============================================================================


class PydanticOrchestrator(BaseGridCodeAgent):
    """Pydantic AI 协调器

    使用 Pydantic AI 原生的 Agent 委托模式协调多个专家代理。

    工作流程:
    1. 用户查询 -> OrchestratorAgent
    2. OrchestratorAgent 分析意图，决定调用哪个 @tool
    3. @tool 内部调用 Subagent: result = await subagent.run(query, deps=ctx.deps, usage=ctx.usage)
    4. OrchestratorAgent 综合结果，返回最终答案

    关键特性:
    - 原生委托模式：Subagent 作为工具被调用
    - 依赖注入：通过 ctx.deps 传递共享依赖
    - 使用量聚合：通过 ctx.usage 追踪所有 token 消耗

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
        enabled_subagents: list[str] | None = None,
    ):
        """初始化 Pydantic AI 协调器

        Args:
            reg_id: 默认规程标识
            model: LLM 模型名称
            mcp_config: MCP 连接配置
            status_callback: 状态回调
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
            ollama_base = settings.llm_base_url
            if not ollama_base.endswith("/v1"):
                ollama_base = ollama_base.rstrip("/") + "/v1"
            os.environ["OPENAI_BASE_URL"] = ollama_base
            self._model = f"openai:{self._model_name}"
        else:
            self._model = f"openai:{self._model_name}"

        # MCP 连接管理器
        self._mcp_manager = get_mcp_manager(mcp_config)

        # 延迟初始化的组件
        self._mcp_server: MCPServerStdio | None = None
        self._orchestrator_agent: Agent | None = None
        self._subagent_builders: dict[SubagentType, SubagentBuilder] = {}

        # 工具调用追踪
        self._tool_calls: list[dict] = []
        self._sources: list[str] = []

        # 连接状态
        self._connected = False

        logger.info(
            f"PydanticOrchestrator initialized: model={self._model}, "
            f"enabled_subagents={self._enabled_subagents}"
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

            # 创建 Orchestrator Agent 和 Subagent Builders
            self._orchestrator_agent, self._subagent_builders = create_orchestrator_agent(
                self._model,
                self._mcp_server,
                self._enabled_subagents,
            )

            self._connected = True

            logger.debug(
                f"Orchestrator initialized with subagents: "
                f"{list(self._subagent_builders.keys())}"
            )

    async def chat(self, message: str) -> AgentResponse:
        """与协调器对话

        Args:
            message: 用户消息

        Returns:
            AgentResponse
        """
        await self._ensure_initialized()

        # 重置追踪
        self._tool_calls = []
        self._sources = []

        start_time = time.time()

        # 发送思考开始事件
        await self._callback.on_event(thinking_event(start=True))

        try:
            # 构建依赖
            deps = OrchestratorDependencies(
                reg_id=self.reg_id,
                mcp_server=self._mcp_server,
                subagent_builders=self._subagent_builders,
                subagent_agents={},  # 延迟初始化
                hints={},
            )

            # 执行 Orchestrator Agent
            result = await self._orchestrator_agent.run(message, deps=deps)

            # 提取工具调用和来源
            self._extract_tool_calls_and_sources(result)

            # 获取输出内容
            content = result.output if isinstance(result.output, str) else str(result.output)

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

            # 记录使用量
            usage = result.usage()
            logger.debug(
                f"Usage: input_tokens={usage.input_tokens}, "
                f"output_tokens={usage.output_tokens}, "
                f"requests={usage.requests}, "
                f"tool_calls={usage.tool_calls}"
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

    def _extract_tool_calls_and_sources(self, result: Any) -> None:
        """从结果中提取工具调用和来源"""
        import json

        for msg in result.all_messages():
            if hasattr(msg, "parts"):
                for part in msg.parts:
                    # ToolCallPart
                    if hasattr(part, "tool_name") and hasattr(part, "args"):
                        self._tool_calls.append({
                            "name": part.tool_name,
                            "input": part.args if isinstance(part.args, dict) else {},
                        })

                    # ToolReturnPart
                    if hasattr(part, "content"):
                        self._extract_sources_from_content(part.content)

    def _extract_sources_from_content(self, content: Any) -> None:
        """从内容中提取来源信息"""
        import json

        if content is None:
            return

        if isinstance(content, dict):
            if "source" in content and content["source"]:
                self._sources.append(str(content["source"]))
            for value in content.values():
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

    async def reset(self) -> None:
        """重置会话状态"""
        self._tool_calls = []
        self._sources = []

        # 重置所有 Subagent Builder 追踪
        for builder in self._subagent_builders.values():
            builder.reset_tracking()

        logger.debug("Session reset")

    async def close(self) -> None:
        """关闭连接"""
        self._orchestrator_agent = None
        self._subagent_builders = {}
        self._connected = False

        logger.debug("Orchestrator closed")

    async def __aenter__(self) -> "PydanticOrchestrator":
        """异步上下文管理器入口"""
        await self._ensure_initialized()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        await self.close()
