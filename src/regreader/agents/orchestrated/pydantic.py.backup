"""Pydantic AI Orchestrator 实现

使用 Pydantic AI 原生 @tool 委托模式实现 LLM 自主选择子智能体。

架构:
    PydanticOrchestrator
        ├── Main Agent (协调器)
        │   └── 根据子智能体描述自主选择
        └── Subagents (专家代理，通过 @tool 注册)
            ├── SearchSubagent
            ├── TableSubagent
            ├── ReferenceSubagent
            └── DiscoverySubagent

关键变更:
- 移除 SubagentBuilder（硬编码构建）
- 使用 @tool 装饰器动态注册子智能体委托工具
- 工具的 docstring 使用 SubagentConfig.description
- LLM 根据 docstring 自主决策调用哪个工具
"""

import os
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from loguru import logger

from regreader.agents.base import AgentResponse
from regreader.agents.orchestrated.base import BaseOrchestrator
from regreader.agents.shared.callbacks import NullCallback, StatusCallback
from regreader.agents.shared.events import (
    response_complete_event,
    text_delta_event,
    thinking_event,
)
from regreader.agents.shared.mcp_connection import MCPConnectionConfig, get_mcp_manager
from regreader.core.config import get_settings
from regreader.orchestration.analyzer import QueryAnalyzer
from regreader.orchestration.coordinator import Coordinator
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
# Dependencies
# ============================================================================


@dataclass
class SubagentDependencies:
    """Subagent 共享依赖

    通过 ctx.deps 传递给 Subagent。

    Attributes:
        reg_id: 规程 ID
        mcp_server: MCP Server
        hints: 额外提示信息
    """

    reg_id: str | None = None
    mcp_server: Any = None  # MCPServerStdio
    hints: dict[str, Any] = field(default_factory=dict)


@dataclass
class OrchestratorDependencies:
    """Orchestrator 共享依赖

    通过 ctx.deps 传递给 Orchestrator 和所有 Subagent。

    Attributes:
        reg_id: 规程 ID
        mcp_server: MCP Server
        subagent_agents: 已构建的 Subagent Agent 映射
        hints: 额外提示信息
    """

    reg_id: str | None = None
    mcp_server: Any = None  # MCPServerStdio
    subagent_agents: dict[SubagentType, Any] = field(default_factory=dict)  # Agent instances
    hints: dict[str, Any] = field(default_factory=dict)


# ============================================================================
# PydanticOrchestrator Class
# ============================================================================


class PydanticOrchestrator(BaseOrchestrator):
    """Pydantic AI 协调器（继承 BaseOrchestrator）

    使用 Pydantic AI 原生的 @tool 委托模式实现 LLM 自主选择子智能体。

    工作流程:
    1. QueryAnalyzer 提取查询提示（hints）
    2. Main Agent 根据工具 docstring（SubagentConfig.description）自主选择
    3. 通过 @tool 调用选定的子智能体
    4. 子智能体执行并返回结果

    特性:
    - LLM 自主决策：根据 @tool 的 docstring 选择子智能体
    - 上下文隔离：每个 Subagent 持有独立的 Agent 实例
    - 原生委托：使用 Pydantic AI 的 @tool 机制
    - 继承 BaseOrchestrator：共享上下文构建、来源提取等基础设施

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
        coordinator: "Coordinator | None" = None,
    ):
        """初始化 Pydantic AI 协调器

        Args:
            reg_id: 默认规程标识
            model: LLM 模型名称
            mcp_config: MCP 连接配置
            status_callback: 状态回调
            enabled_subagents: 启用的 Subagent 列表
            coordinator: 协调器实例（可选，用于文件系统追踪）
        """
        # 调用 BaseOrchestrator 构造函数
        super().__init__(
            reg_id=reg_id,
            use_coordinator=coordinator is not None,
            callback=status_callback or NullCallback(),
        )

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

        # 查询分析器（仅提取 hints）
        self._analyzer = QueryAnalyzer()

        # 协调器（可选）
        self._coordinator = coordinator

        # 延迟初始化的组件
        self._mcp_server: MCPServerStdio | None = None
        self._main_agent: Agent | None = None
        self._subagents: dict[SubagentType, Agent] = {}

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
        if not self._initialized:
            # 获取 MCP Server
            self._mcp_server = self._mcp_manager.get_pydantic_mcp_server()

            # 创建 Subagents
            self._subagents = self._create_subagents()

            # 创建 Main Agent
            self._main_agent = self._create_main_agent()

            self._initialized = True

            logger.debug(
                f"Orchestrator initialized with subagents: "
                f"{list(self._subagents.keys())}"
            )

    def _create_subagents(self) -> dict[SubagentType, Agent]:
        """创建 Subagent Agent 实例

        为每个启用的子智能体创建独立的 Agent 实例。

        Returns:
            SubagentType 到 Agent 的映射
        """
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

            # 创建 Agent 实例
            agent = self._create_subagent_agent(config)
            subagents[agent_type] = agent

            logger.debug(f"Created subagent: {config.name} ({agent_type.value})")

        return subagents

    def _create_subagent_agent(self, config) -> Agent:
        """为单个子智能体创建 Agent 实例

        Args:
            config: SubagentConfig

        Returns:
            Agent 实例
        """
        # 构建系统提示词
        instructions = self._build_subagent_domain_prompt(config)

        # 创建 Agent
        agent = Agent(
            self._model,
            deps_type=SubagentDependencies,
            system_prompt=instructions,
        )

        return agent

    def _build_subagent_domain_prompt(self, config) -> str:
        """构建子智能体的领域特定提示词

        Args:
            config: SubagentConfig

        Returns:
            领域特定提示词
        """
        # 获取允许的工具列表
        from regreader.agents.shared.mcp_config import get_tool_name
        allowed_tools = [get_tool_name(name) for name in config.tools]
        tools_display = ", ".join(allowed_tools) if allowed_tools else "无"

        prompt = f"""# 角色定位
你是 {config.name}，专门负责{config.description}。

# 电力规程领域知识

## 文档结构规范
- **章节编号格式**：X.X.X.X（如 2.1.4.1.6）
- **表格命名规则**：表X-X（如 表6-2）
- **注释引用**：注1、注2、注①、注一、选项A、选项B、方案甲等变体
- **引用语法**："见第X章"、"参见X.X节"、"详见附录X"、"见注X"

## 工具使用约束
你**只能使用**以下MCP工具：
{tools_display}

**严格限制**：不得使用其他未列出的工具，不得尝试绕过工具限制。

## 检索策略
1. **精确匹配优先**：优先使用章节号、表格号、注释ID等精确标识符
2. **语义搜索作为补充**：找不到精确匹配时使用语义搜索
3. **表格查询完整性**：表格查询必须返回完整结构，注意跨页表格
4. **注释引用追踪**：发现注释引用时必须回溯到原文获取完整内容

## 输出要求（关键）
**关键规则：在调用工具后，必须用自然语言总结工具返回的结果，而不是返回原始工具输出。**

- 将搜索到的内容片段整理成自然语言描述
- 附带准确的来源信息（规程名 + 页码 + 章节）
- 如果发现「见注X」或「见第X章」等引用，在总结中明确指出
- 如果工具返回JSON格式，提取关键信息并用自然语言表达
- 使用清晰的段落结构，避免直接输出原始工具数据

示例输出格式：
```
根据搜索结果，在《安规_2024》规程中找到以下相关内容：

**第X章节（P123）**：
具体内容描述...

**来源**：angui_2024 P123（第X章 > X.X节）
```
"""
        return prompt

    def _create_main_agent(self) -> Agent:
        """创建 Main Agent（协调器）

        Main Agent 负责：
        1. 理解用户查询
        2. 根据工具 docstring（SubagentConfig.description）选择合适的工具
        3. 通过 @tool 调用选定的子智能体

        Returns:
            Main Agent 实例
        """
        # 构建 Main Agent 提示词
        instructions = self._build_main_agent_prompt()

        # 创建 Main Agent
        agent = Agent(
            self._model,
            deps_type=OrchestratorDependencies,
            system_prompt=instructions,
        )

        # 动态注册子智能体委托工具
        self._register_subagent_tools(agent)

        logger.debug(f"Created Main Agent with {len(self._subagents)} tools")

        return agent

    def _build_main_agent_prompt(self) -> str:
        """构建 Main Agent 提示词

        包含所有启用的子智能体描述，让 LLM 自主选择。

        Returns:
            Main Agent 提示词
        """
        # 收集所有启用的子智能体描述
        subagent_descriptions = []
        for agent_type, agent in self._subagents.items():
            config = SUBAGENT_CONFIGS.get(agent_type)
            if config and config.enabled:
                subagent_descriptions.append(f"""
### {config.name}
{config.description}
""")

        descriptions_text = "".join(subagent_descriptions)

        prompt = f"""你是 RegReader 协调器，负责将用户查询分派给合适的专家子智能体。

# 可用的专家子智能体

{descriptions_text}

# 你的职责

1. **理解用户查询**：分析用户的问题，识别查询意图
2. **选择合适的子智能体**：根据上述描述，选择最适合处理该查询的子智能体
3. **调用工具**：使用对应的工具（call_search_agent、call_table_agent 等）调用子智能体

# 决策指南

- 如果查询涉及**搜索关键词、浏览目录、读取章节**，调用 call_search_agent
- 如果查询涉及**表格查询、表格提取、注释查找**，调用 call_table_agent
- 如果查询涉及**交叉引用、"见第X章"、"参见表X"**，调用 call_reference_agent
- 如果查询涉及**语义分析、相似内容、章节对比**，调用 call_discovery_agent（如果启用）

# 重要提示

- **不要自己执行查询**：你的职责是选择和调用工具，不是直接回答
- **立即调用工具**：分析完查询后，立即调用对应的工具
- **信任子智能体**：子智能体会处理所有细节，你只需选择正确的专家
"""

        return prompt

    def _register_subagent_tools(self, agent: Agent) -> None:
        """动态注册子智能体委托工具

        为每个启用的子智能体注册 @tool 装饰器。
        工具的 docstring 使用 SubagentConfig.description。

        Args:
            agent: Main Agent 实例
        """
        # 为每个启用的子智能体注册工具
        for agent_type, subagent in self._subagents.items():
            config = SUBAGENT_CONFIGS.get(agent_type)
            if not config:
                continue

            # 根据类型注册对应的工具
            if agent_type == SubagentType.SEARCH:
                self._register_search_tool(agent, config)
            elif agent_type == SubagentType.TABLE:
                self._register_table_tool(agent, config)
            elif agent_type == SubagentType.REFERENCE:
                self._register_reference_tool(agent, config)
            elif agent_type == SubagentType.DISCOVERY:
                self._register_discovery_tool(agent, config)

    def _register_search_tool(self, agent: Agent, config) -> None:
        """注册 SearchAgent 工具"""
        @agent.tool
        async def call_search_agent(
            ctx: "RunContext[OrchestratorDependencies]",
            query: str,
        ) -> str:
            f"""{config.description}

Args:
    query: 搜索查询内容
"""
            return await self._invoke_subagent(ctx, SubagentType.SEARCH, query)

    def _register_table_tool(self, agent: Agent, config) -> None:
        """注册 TableAgent 工具"""
        @agent.tool
        async def call_table_agent(
            ctx: "RunContext[OrchestratorDependencies]",
            query: str,
        ) -> str:
            f"""{config.description}

Args:
    query: 表格相关查询内容
"""
            return await self._invoke_subagent(ctx, SubagentType.TABLE, query)

    def _register_reference_tool(self, agent: Agent, config) -> None:
        """注册 ReferenceAgent 工具"""
        @agent.tool
        async def call_reference_agent(
            ctx: "RunContext[OrchestratorDependencies]",
            query: str,
        ) -> str:
            f"""{config.description}

Args:
    query: 引用相关查询内容
"""
            return await self._invoke_subagent(ctx, SubagentType.REFERENCE, query)

    def _register_discovery_tool(self, agent: Agent, config) -> None:
        """注册 DiscoveryAgent 工具"""
        @agent.tool
        async def call_discovery_agent(
            ctx: "RunContext[OrchestratorDependencies]",
            query: str,
        ) -> str:
            f"""{config.description}

Args:
    query: 发现相关查询内容
"""
            return await self._invoke_subagent(ctx, SubagentType.DISCOVERY, query)

    async def _invoke_subagent(
        self,
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
        from regreader.agents.shared.events import phase_change_event, tool_end_event, tool_start_event

        deps = ctx.deps
        subagent = self._subagents.get(agent_type)

        if subagent is None:
            return f"错误: {agent_type.value} 专家代理未启用"

        # 发送阶段变化事件（子智能体切换）
        await self.callback.on_event(
            phase_change_event(
                phase=f"subagent_{agent_type.value}",
                description=f"切换到 {agent_type.value} 专家代理",
            )
        )

        # 发送工具调用开始事件（将子智能体调用视为工具调用）
        tool_name = f"invoke_{agent_type.value}"
        tool_id = f"{agent_type.value}_{id(query)}"
        start_time = datetime.now()

        await self.callback.on_event(
            tool_start_event(
                tool_name=tool_name,
                tool_input={"query": query, "agent_type": agent_type.value},
                tool_id=tool_id,
            )
        )

        # 创建 Subagent 依赖
        subagent_deps = SubagentDependencies(
            reg_id=deps.reg_id,
            mcp_server=deps.mcp_server,
            hints=deps.hints,
        )

        # 调用 Subagent（传递 usage 以聚合使用量）
        try:
            result = await subagent.run(
                query,
                deps=subagent_deps,
                usage=ctx.usage,  # 关键：传递 usage 以聚合 token 消耗
            )

            # 提取来源信息
            self._extract_sources_from_result(result)

            # 计算执行耗时
            duration = datetime.now() - start_time
            duration_ms = duration.total_seconds() * 1000

            # 返回内容
            content = result.output if isinstance(result.output, str) else str(result.output)

            # 发送工具调用完成事件
            await self.callback.on_event(
                tool_end_event(
                    tool_name=tool_name,
                    tool_id=tool_id,
                    duration_ms=duration_ms,
                    result_summary=content[:100] if content else "",
                    tool_input={"query": query, "agent_type": agent_type.value},
                )
            )

            return content

        except Exception as e:
            logger.exception(f"Subagent {agent_type.value} execution error: {e}")

            # 发送工具调用错误事件
            from regreader.agents.shared.events import tool_error_event

            await self.callback.on_event(
                tool_error_event(
                    tool_name=tool_name,
                    error=str(e),
                    tool_id=tool_id,
                )
            )

            return f"错误: {str(e)}"

    async def _execute_orchestration(
        self,
        query: str,
        context_info: str,
    ) -> str:
        """执行 Pydantic AI 编排（Delegation Pattern）

        Args:
            query: 用户查询
            context_info: 上下文信息

        Returns:
            最终回答内容
        """
        # 构建完整提示
        enhanced_message = f"{query}\n\n{context_info}" if context_info else query

        # 构建依赖
        deps = OrchestratorDependencies(
            reg_id=self.reg_id,
            mcp_server=self._mcp_server,
            subagent_agents={},  # 延迟初始化
            hints={},  # hints 已经在 context_info 中
        )

        # 执行 Main Agent
        result = await self._main_agent.run(enhanced_message, deps=deps)

        # 提取工具调用和来源
        self._extract_tool_calls_and_sources(result)

        # 获取输出内容
        content = result.output if isinstance(result.output, str) else str(result.output)

        # 记录使用量
        usage = result.usage()
        logger.debug(
            f"Usage: input_tokens={usage.input_tokens}, "
            f"output_tokens={usage.output_tokens}, "
            f"requests={usage.requests}, "
            f"tool_calls={usage.tool_calls}"
        )

        return content

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

    def _extract_sources_from_result(self, result: Any) -> None:
        """从 Subagent 结果中提取来源信息"""
        if hasattr(result, "all_messages"):
            for msg in result.all_messages():
                if hasattr(msg, "parts"):
                    for part in msg.parts:
                        if hasattr(part, "content"):
                            self._extract_sources_from_content(part.content)

    async def reset(self) -> None:
        """重置会话状态"""
        self._tool_calls = []
        self._sources = []

        logger.debug("Session reset")

    async def close(self) -> None:
        """关闭连接"""
        self._main_agent = None
        self._subagents = {}
        self._initialized = False

        logger.debug("Orchestrator closed")

    async def __aenter__(self) -> "PydanticOrchestrator":
        """异步上下文管理器入口"""
        await self._ensure_initialized()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        await self.close()
