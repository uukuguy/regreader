"""Claude Agent SDK Orchestrator 实现

使用 Claude SDK 原生 Handoff Pattern 实现 LLM 自主选择子智能体。

架构:
    ClaudeOrchestrator
        ├── Main Agent (协调器)
        │   └── 根据子智能体描述自主选择
        └── Subagents (专家代理，通过 handoffs 注册)
            ├── SearchSubagent
            ├── TableSubagent
            ├── ReferenceSubagent
            └── DiscoverySubagent

关键变更:
- 移除 SubagentRouter（硬编码路由）
- 移除 QueryAnalyzer.analyze()（意图分析）
- 使用 QueryAnalyzer.extract_hints() 提取提示信息
- LLM 根据子智能体的 description 自主决策
"""

import time
from datetime import datetime
from typing import TYPE_CHECKING

from loguru import logger

from regreader.agents.base import AgentResponse
from regreader.agents.orchestrated.base import BaseOrchestrator
from regreader.agents.shared.callbacks import NullCallback, StatusCallback
from regreader.agents.claude.subagents import create_claude_subagent
from regreader.agents.shared.events import (
    response_complete_event,
    text_delta_event,
    thinking_event,
)
from regreader.agents.shared.result_parser import parse_tool_result
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

# Claude Agent SDK imports
try:
    from claude_agent_sdk import (
        AgentDefinition,
        ClaudeAgentOptions,
        ClaudeSDKClient,
        ClaudeSDKError,
        ResultMessage,
    )

    HAS_CLAUDE_SDK = True
except ImportError:
    HAS_CLAUDE_SDK = False
    AgentDefinition = None  # type: ignore
    ClaudeAgentOptions = None  # type: ignore
    ClaudeSDKClient = None  # type: ignore
    ClaudeSDKError = Exception  # type: ignore
    ResultMessage = None  # type: ignore

if TYPE_CHECKING:
    pass


class ClaudeOrchestrator(BaseOrchestrator):
    """Claude Agent SDK 协调器（继承 BaseOrchestrator）

    使用 Handoff Pattern 实现 LLM 自主选择子智能体。

    工作流程:
    1. QueryAnalyzer 提取查询提示（hints）
    2. Main Agent 根据子智能体描述自主选择
    3. 通过 handoff 切换到选定的子智能体
    4. 子智能体执行并返回结果

    特性:
    - LLM 自主决策：根据 SubagentConfig.description 选择子智能体
    - 上下文隔离：每个 Subagent 持有独立的 Agent 实例
    - 原生 Handoff：使用 Claude SDK 的 handoffs 机制
    - 继承 BaseOrchestrator：共享上下文构建、来源提取等基础设施

    Usage:
        async with ClaudeOrchestrator(reg_id="angui_2024") as agent:
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
        use_preset: bool = True,
        coordinator: "Coordinator | None" = None,
    ):
        """初始化 Claude 协调器

        Args:
            reg_id: 默认规程标识
            model: Claude 模型名称（如 haiku, sonnet）
            mcp_config: MCP 连接配置
            status_callback: 状态回调
            enabled_subagents: 启用的 Subagent 列表
            use_preset: 是否使用 preset: "claude_code"（默认True，使用Anthropic官方最佳实践）
            coordinator: 协调器实例（可选，用于文件系统追踪）
        """
        # 调用 BaseOrchestrator 构造函数
        super().__init__(
            reg_id=reg_id,
            use_coordinator=coordinator is not None,
            callback=status_callback or NullCallback(),
        )

        if not HAS_CLAUDE_SDK:
            raise ImportError(
                "Claude Agent SDK not installed. Please run: pip install claude-agent-sdk"
            )

        settings = get_settings()

        # Claude 使用 Anthropic 专用配置
        self._model = model or settings.anthropic_model_name or ""
        self._use_preset = use_preset

        # 确定启用的 Subagent
        if enabled_subagents is None:
            enabled_subagents = ["search", "table", "reference"]
        self._enabled_subagents = set(enabled_subagents)

        # MCP 连接管理器
        self._mcp_manager = get_mcp_manager(mcp_config)

        # 查询分析器（仅提取 hints）
        self._analyzer = QueryAnalyzer()

        # 协调器（可选）
        self._coordinator = coordinator

        # Subagent 配置（延迟初始化）
        # 注意：不再持有 Agent 实例，而是 AgentDefinition 配置字典
        self._subagents: dict[str, AgentDefinition] = {}

        model_display = self._model or "(SDK default)"
        logger.info(
            f"ClaudeOrchestrator initialized: model={model_display}, "
            f"enabled_subagents={self._enabled_subagents}, "
            f"use_preset={self._use_preset}"
        )

    @property
    def name(self) -> str:
        return "ClaudeOrchestrator"

    @property
    def model(self) -> str:
        return self._model

    def _get_regulations(self) -> list[dict]:
        """获取规程列表（复用单智能体的逻辑）

        Returns:
            规程信息列表
        """
        from regreader.storage import PageStore
        from regreader.core.config import get_settings

        settings = get_settings()
        page_store = PageStore(settings.pages_dir)

        # 使用缓存（如果已存在）
        if not hasattr(self, '_regulations_cache'):
            regulations = page_store.list_regulations()
            self._regulations_cache = [
                {
                    "reg_id": r.reg_id,
                    "title": r.title,
                    "keywords": r.keywords,
                    "scope": r.scope,
                    "description": r.description,
                }
                for r in regulations
            ]
            logger.debug(f"加载规程列表: {len(self._regulations_cache)} 个")

        return self._regulations_cache

    async def _ensure_initialized(self) -> None:
        """确保组件已初始化"""
        if not self._initialized:
            # 创建 Subagent 配置字典
            self._subagents = self._create_subagents()

            self._initialized = True

            logger.debug(f"Orchestrator initialized with subagents: {list(self._subagents.keys())}")

    def _create_subagents(self) -> dict[str, AgentDefinition]:
        """创建 Subagent 配置字典

        为每个启用的子智能体创建 AgentDefinition 配置。

        Returns:
            子智能体名称（字符串）到 AgentDefinition 的映射（用于 ClaudeAgentOptions.agents）
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

            # 创建 AgentDefinition 配置
            agent = self._create_subagent_definition(config)
            # 使用 agent_type.value 作为键（例如："search", "table"）
            subagents[agent_type.value] = agent

            logger.debug(f"Created subagent: {config.name} ({agent_type.value})")

        return subagents

    def _create_subagent_definition(self, config) -> AgentDefinition:
        """为单个子智能体创建 AgentDefinition 配置

        Args:
            config: SubagentConfig

        Returns:
            AgentDefinition 配置对象
        """
        # 构建系统提示词
        if self._use_preset:
            # Preset 模式：精简的领域特定指令
            prompt = self._build_subagent_domain_prompt(config)
        else:
            # 手动模式：完整提示词
            prompt = config.system_prompt_template

        # 获取允许的工具列表
        from regreader.agents.shared.mcp_config import get_tool_name

        allowed_tools = [get_tool_name(name) for name in config.tools]

        # 创建 AgentDefinition（使用正确的参数）
        agent_def = AgentDefinition(
            description=config.description,  # 告诉主智能体何时使用此子智能体
            prompt=prompt,  # 定义子智能体的行为和专业知识
            tools=allowed_tools,  # 限制子智能体可以使用的工具
            model="inherit",  # 继承主智能体的模型（或指定 "sonnet", "opus", "haiku"）
        )

        return agent_def

    def _build_subagent_domain_prompt(self, config) -> str:
        """构建子智能体的领域特定提示词（动态生成版本）

        Args:
            config: SubagentConfig

        Returns:
            领域特定提示词
        """
        # 使用统一的动态生成函数
        from regreader.agents.prompts import (
            generate_role_for_subagent,
            generate_tool_section_for_tools,
            generate_workflow_for_tools,
        )

        # 1. 生成角色定义
        role = generate_role_for_subagent(config.agent_type)

        # 2. 动态生成工具描述（从 config.tools）
        tool_section = generate_tool_section_for_tools(config.tools)

        # 3. 生成针对性工作流程
        workflow = generate_workflow_for_tools(config.tools)

        # 4. 组装提示词
        prompt = f"{role}\n\n# 可用工具\n{tool_section}\n\n{workflow}"

        # 5. 电力规程领域知识（保持原有）
        domain_knowledge = """
## 电力规程领域知识

### 文档结构规范
- **章节编号格式**：X.X.X.X（如 2.1.4.1.6）
- **表格命名规则**：表X-X（如 表6-2）
- **注释引用**：注1、注2、注①、注一、选项A、选项B、方案甲等变体
- **引用语法**："见第X章"、"参见X.X节"、"详见附录X"、"见注X"

### 检索策略
1. **精确匹配优先**：优先使用章节号、表格号、注释ID等精确标识符
2. **语义搜索作为补充**：找不到精确匹配时使用语义搜索
3. **表格查询完整性**：表格查询必须返回完整结构，注意跨页表格
4. **注释引用追踪**：发现注释引用时必须回溯到原文获取完整内容
"""

        # 6. 输出要求（保持原有）
        output_requirements = """
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

        # 7. 追加专项任务描述
        if config.description and config.description != config.name:
            task_desc = f"\n\n# 专项任务\n{config.description}"
        else:
            task_desc = ""

        # 8. 组装完整提示词
        full_prompt = f"{prompt}\n\n{domain_knowledge}\n{output_requirements}{task_desc}"

        return full_prompt

    async def _execute_orchestration(
        self,
        query: str,
        context_info: str,
    ) -> str:
        """执行 Claude SDK 编排（Handoff Pattern）

        Args:
            query: 用户查询
            context_info: 上下文信息

        Returns:
            最终回答内容
        """
        # 构建完整查询（包含上下文）
        enhanced_message = f"{query}\n\n{context_info}" if context_info else query

        # 构建 Agent 选项
        options = self._build_main_agent_options()

        # 执行 Main Agent
        final_content = ""
        async with ClaudeSDKClient(options=options) as client:
            # 发送查询
            await client.query(enhanced_message)

            # 接收响应
            async for event in client.receive_response():
                # 处理事件（提取工具调用和来源）
                await self._process_event(event)

                # 检查最终结果
                if ResultMessage is not None and isinstance(event, ResultMessage):
                    if event.result:
                        final_content = event.result
                        logger.debug(
                            f"Got ResultMessage with content length={len(final_content)}"
                        )
                    break

        # 发送文本事件
        if final_content:
            await self._send_event(text_delta_event(final_content))

        return final_content

    def _build_main_prompt(self) -> str:
        """构建主智能体的系统提示词（与单智能体模式一致）

        主智能体应该和单智能体使用相同的提示词，子智能体用于：
        1. 上下文隔离（不同任务不污染主线上下文）
        2. 并行执行（同时执行多个独立子任务）

        Returns:
            主智能体的系统提示词
        """
        from regreader.agents.prompts import get_optimized_prompt_with_domain

        # 获取规程列表（复用单智能体的逻辑）
        regulations = self._get_regulations()

        # 使用和单智能体完全相同的提示词
        settings = get_settings()
        include_advanced = getattr(settings, "enable_advanced_tools", False)

        base_prompt = get_optimized_prompt_with_domain(include_advanced, regulations)

        # 追加当前规程信息
        if self.reg_id:
            base_prompt += f"\n\n# 当前规程\n默认规程: {self.reg_id}"

        # 追加 Orchestrator 特有的说明
        orchestrator_note = """

# Orchestrator 模式说明

你现在运行在 Orchestrator 模式下，可以使用子智能体来：
1. **上下文隔离**：将复杂任务分解为独立的子任务，每个子任务在隔离的上下文中执行
2. **并行执行**：多个独立的子任务可以同时执行，提高效率

## 可用的子智能体
{subagent_descriptions}

## 如何使用子智能体

当你需要执行子任务时，可以使用 **Task 工具**调用子智能体：
```
Task(subagent_type="search", query="获取目录结构")
Task(subagent_type="search", query="在第六章搜索母线失压")
Task(subagent_type="table", query="查找锦苏安控的配置表格")
```

**重要**：
- 子智能体会返回**处理后的内容摘要**，而非原始工具输出
- 你需要整合多个子智能体的结果，生成最终答案
- 简单查询可以直接使用 MCP 工具，无需调用子智能体
"""

        # 收集子智能体描述（简要版本）
        subagent_descriptions = []
        for agent_name, agent_def in self._subagents.items():
            subagent_descriptions.append(f"- **{agent_name}**: {agent_def.description}")

        descriptions_text = "\n".join(subagent_descriptions)

        return base_prompt + orchestrator_note.format(subagent_descriptions=descriptions_text)

    def _build_main_agent_options(self) -> ClaudeAgentOptions:
        """构建 Main Agent 选项

        根据正确的 SDK API，将子智能体配置添加到 ClaudeAgentOptions.agents 中。

        Returns:
            ClaudeAgentOptions
        """
        # 禁用内置工具（避免与MCP工具冲突）
        disallowed = [
            "Bash",
            "Read",
            "Write",
            "Edit",
            "Glob",
            "Grep",
            "LS",
            "MultiEdit",
            "NotebookEdit",
            "NotebookRead",
            "TodoRead",
            "TodoWrite",
            "WebFetch",
            "WebSearch",
        ]

        # 获取所有子智能体的工具列表
        from regreader.agents.shared.mcp_config import get_tool_name

        all_tools = set()
        for agent_name in self._subagents.keys():
            # 从 SubagentType 获取配置
            agent_type = SubagentType(agent_name)
            config = SUBAGENT_CONFIGS.get(agent_type)
            if config:
                all_tools.update(get_tool_name(name) for name in config.tools)

        # 添加 Task 工具（必须包含，用于调用子智能体）
        all_tools.add("Task")

        # 构建主智能体的系统提示词
        main_prompt = self._build_main_prompt()

        # 基础选项
        options_kwargs = {
            "mcp_servers": self._mcp_manager.get_claude_sdk_config(),
            "allowed_tools": list(all_tools),  # 包含 Task 工具和所有子智能体工具
            "disallowed_tools": disallowed,
            "max_turns": 10,
            "permission_mode": "bypassPermissions",
            "include_partial_messages": False,
            "agents": self._subagents,  # 子智能体配置字典
        }

        # 根据配置选择提示词模式
        if self._use_preset:
            # Preset模式：使用 claude_code preset + 主智能体提示词
            options_kwargs["system_prompt"] = {
                "type": "preset",
                "preset": "claude_code",
                "append": main_prompt,  # 追加主智能体的协调逻辑
            }
            logger.debug("Using preset: 'claude_code' with main prompt appended")
        else:
            # 手动模式：仅使用主智能体提示词
            options_kwargs["system_prompt"] = main_prompt
            logger.debug("Using manual mode with custom main prompt")

        # 只有指定模型时才传递
        if self._model:
            options_kwargs["model"] = self._model

        return ClaudeAgentOptions(**options_kwargs)

    async def _process_event(self, event) -> None:
        """处理 SDK 事件

        提取工具调用和来源信息，并发送回调事件。

        Args:
            event: SDK 事件
        """
        from claude_agent_sdk import (
            AssistantMessage,
            ToolResultBlock,
            ToolUseBlock,
            UserMessage,
        )

        from regreader.agents.shared.events import tool_end_event, tool_start_event

        # 记录事件类型
        event_type = type(event).__name__
        logger.debug(f"Processing event: {event_type}")

        # 处理 AssistantMessage
        if isinstance(event, AssistantMessage):
            for block in event.content:
                # ToolUseBlock - 工具调用
                if isinstance(block, ToolUseBlock):
                    tool_name = block.name
                    tool_input = block.input if isinstance(block.input, dict) else {}
                    tool_id = getattr(block, "id", "") or ""

                    self._tool_calls.append(
                        {
                            "name": tool_name,
                            "input": tool_input,
                            "tool_id": tool_id,
                            "start_time": datetime.now(),
                        }
                    )

                    logger.debug(f"Tool call: {tool_name}")

                    # 发送工具调用开始事件
                    await self.callback.on_event(
                        tool_start_event(
                            tool_name=tool_name,
                            tool_input=tool_input,
                            tool_id=tool_id,
                        )
                    )

                # ToolResultBlock - 工具结果
                elif isinstance(block, ToolResultBlock):
                    content = getattr(block, "content", None)
                    tool_use_id = getattr(block, "tool_use_id", "") or ""

                    # 更新对应的工具调用
                    for tc in reversed(self._tool_calls):
                        if tc.get("tool_id") == tool_use_id:
                            tc["output"] = content

                            # 计算执行耗时
                            duration_ms = 0
                            if "start_time" in tc:
                                duration = datetime.now() - tc["start_time"]
                                duration_ms = duration.total_seconds() * 1000

                            # 使用 parse_tool_result 提取详细结果摘要
                            summary = parse_tool_result(tc["name"], content)

                            # 发送工具调用完成事件
                            await self.callback.on_event(
                                tool_end_event(
                                    tool_name=tc["name"],
                                    tool_id=tool_use_id,
                                    duration_ms=duration_ms,
                                    result_summary=summary.content_preview or "",
                                    result_count=summary.result_count,
                                    result_type=summary.result_type,
                                    chapter_count=summary.chapter_count,
                                    page_sources=summary.page_sources,
                                    content_preview=summary.content_preview,
                                    tool_input=tc.get("input"),
                                )
                            )
                            break

                    # 提取来源
                    self._extract_sources(content)

        # 处理 UserMessage
        if isinstance(event, UserMessage):
            for block in event.content:
                # ToolResultBlock - 工具结果
                if isinstance(block, ToolResultBlock):
                    content = getattr(block, "content", None)
                    tool_use_id = getattr(block, "tool_use_id", "") or ""

                    # 更新对应的工具调用
                    for tc in reversed(self._tool_calls):
                        if tc.get("tool_id") == tool_use_id:
                            tc["output"] = content

                            # 计算执行耗时
                            duration_ms = 0
                            if "start_time" in tc:
                                duration = datetime.now() - tc["start_time"]
                                duration_ms = duration.total_seconds() * 1000

                            # 使用 parse_tool_result 提取详细结果摘要
                            summary = parse_tool_result(tc["name"], content)

                            # 发送工具调用完成事件
                            await self.callback.on_event(
                                tool_end_event(
                                    tool_name=tc["name"],
                                    tool_id=tool_use_id,
                                    duration_ms=duration_ms,
                                    result_summary=summary.content_preview or "",
                                    result_count=summary.result_count,
                                    result_type=summary.result_type,
                                    chapter_count=summary.chapter_count,
                                    page_sources=summary.page_sources,
                                    content_preview=summary.content_preview,
                                    tool_input=tc.get("input"),
                                )
                            )
                            break

                    # 提取来源
                    self._extract_sources(content)

        # 处理独立的 ToolResultBlock
        if isinstance(event, ToolResultBlock):
            content = getattr(event, "content", None)
            tool_use_id = getattr(event, "tool_use_id", "") or ""

            # 更新对应的工具调用
            for tc in reversed(self._tool_calls):
                if tc.get("tool_id") == tool_use_id:
                    tc["output"] = content

                    # 计算执行耗时
                    duration_ms = 0
                    if "start_time" in tc:
                        duration = datetime.now() - tc["start_time"]
                        duration_ms = duration.total_seconds() * 1000

                    # 使用 parse_tool_result 提取详细结果摘要
                    summary = parse_tool_result(tc["name"], content)

                    # 发送工具调用完成事件
                    await self.callback.on_event(
                        tool_end_event(
                            tool_name=tc["name"],
                            tool_id=tool_use_id,
                            duration_ms=duration_ms,
                            result_summary=summary.content_preview or "",
                            result_count=summary.result_count,
                            result_type=summary.result_type,
                            chapter_count=summary.chapter_count,
                            page_sources=summary.page_sources,
                            content_preview=summary.content_preview,
                            tool_input=tc.get("input"),
                        )
                    )
                    break

            # 提取来源
            self._extract_sources(content)

    async def reset(self) -> None:
        """重置会话状态"""
        self._reset_tracking()
        logger.debug("Session reset")

    async def close(self) -> None:
        """关闭连接"""
        self._subagents = {}
        self._initialized = False

        logger.debug("Orchestrator closed")

    async def __aenter__(self) -> "ClaudeOrchestrator":
        """异步上下文管理器入口"""
        await self._ensure_initialized()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        await self.close()
