"""Claude Agent SDK Subagent 实现

基于 Claude Agent SDK 的 Subagent 实现。
每个 Subagent 是独立的 ClaudeSDKClient 实例，具有过滤的工具集。

架构特点:
- Handoff Pattern: 每个 Subagent 持有独立的 ClaudeSDKClient
- 工具过滤: 通过 allowed_tools 参数限制可用工具
- 上下文隔离: 每个 Subagent 使用独立的系统提示词
"""

import time
from typing import Any

from loguru import logger

from grid_code.agents.mcp_config import get_tool_name
from grid_code.agents.mcp_connection import MCPConnectionManager
from grid_code.subagents.base import BaseSubagent, SubagentContext
from grid_code.subagents.config import SubagentConfig, SubagentType
from grid_code.subagents.result import SubagentResult

# Claude Agent SDK imports
try:
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ClaudeSDKClient,
        ClaudeSDKError,
        ResultMessage,
        TextBlock,
        ThinkingBlock,
        ToolResultBlock,
        ToolUseBlock,
    )

    HAS_CLAUDE_SDK = True
except ImportError:
    HAS_CLAUDE_SDK = False
    AssistantMessage = None  # type: ignore
    ResultMessage = None  # type: ignore
    TextBlock = None  # type: ignore
    ThinkingBlock = None  # type: ignore
    ToolUseBlock = None  # type: ignore
    ToolResultBlock = None  # type: ignore
    ClaudeSDKError = Exception  # type: ignore
    ClaudeAgentOptions = None  # type: ignore
    ClaudeSDKClient = None  # type: ignore


class BaseClaudeSubagent(BaseSubagent):
    """基于 Claude Agent SDK 的 Subagent 基类

    使用 Handoff Pattern，每个实例管理独立的 ClaudeSDKClient。
    通过 allowed_tools 参数实现工具过滤。

    Attributes:
        config: Subagent 配置
        mcp_manager: MCP 连接管理器
        model: Claude 模型名称
    """

    def __init__(
        self,
        config: SubagentConfig,
        model: str,
        mcp_manager: MCPConnectionManager,
        use_preset: bool = True,
    ):
        """初始化 Claude Subagent

        Args:
            config: Subagent 配置
            model: Claude 模型名称（如 haiku, sonnet）
            mcp_manager: MCP 连接管理器
            use_preset: 是否使用 preset: "claude_code"（默认True，使用Anthropic官方最佳实践）
        """
        super().__init__(config)

        if not HAS_CLAUDE_SDK:
            raise ImportError(
                "Claude Agent SDK not installed. "
                "Please run: pip install claude-agent-sdk"
            )

        self._model = model
        self._mcp_manager = mcp_manager
        self._use_preset = use_preset

        # 工具调用追踪
        self._tool_calls: list[dict] = []
        self._sources: list[str] = []

        logger.debug(
            f"Claude Subagent '{self.name}' initialized: "
            f"model={model}, tools={len(config.tools)}, use_preset={use_preset}"
        )

    def _get_allowed_tools(self) -> list[str]:
        """获取允许使用的工具列表

        根据配置中的 tools 列表生成 MCP 工具名称。
        """
        return [get_tool_name(name) for name in self.config.tools]

    def _get_mcp_config(self) -> dict[str, Any]:
        """获取 MCP 服务器配置"""
        return self._mcp_manager.get_claude_sdk_config()

    def _build_system_prompt(self, context: SubagentContext) -> str:
        """构建系统提示词（传统手动模式）

        注入上下文信息到基础提示词。

        Args:
            context: Subagent 上下文

        Returns:
            完整的系统提示词
        """
        prompt = self.config.system_prompt

        # 注入规程标识
        if context.reg_id:
            prompt += f"\n\n# 当前规程\n默认规程: {context.reg_id}"

        # 注入章节范围
        if context.chapter_scope:
            prompt += f"\n章节范围提示: {context.chapter_scope}"

        # 注入提示
        if context.hints:
            hints_str = "\n".join(f"- {k}: {v}" for k, v in context.hints.items())
            prompt += f"\n\n# 提示\n{hints_str}"

        return prompt

    def _build_domain_prompt(self, context: SubagentContext) -> str:
        """构建精简的领域特定指令（preset模式）

        只包含电力规程领域知识，通用逻辑由 preset: "claude_code" 处理。
        提示词长度约 500-700 字，相比手动模式的 1500-2000 字减少 60-70%。

        Args:
            context: Subagent 上下文，包含 query、reg_id、chapter_scope、hints 等

        Returns:
            str: 领域特定提示词，包含：
                - 角色定位和责任描述
                - 电力规程文档结构规范
                - 工具使用约束
                - 检索策略
                - 动态注入的上下文信息

        Example:
            >>> context = SubagentContext(
            ...     query="表6-2中注1的内容",
            ...     reg_id="angui_2024",
            ...     chapter_scope="第六章",
            ...     hints={"table_hint": "表6-2", "annotation_hint": "注1"},
            ...     max_iterations=5
            ... )
            >>> prompt = subagent._build_domain_prompt(context)
            >>> print(len(prompt))  # ~600 字符
            >>> assert "表6-2" in prompt
            >>> assert "注1" in prompt

        Note:
            此方法仅在 use_preset=True 时使用。使用 preset: "claude_code" 时，
            通用的工具使用策略、任务规划、错误处理等由 Anthropic 官方 preset 提供，
            此方法只需关注电力规程领域的特定知识。
        """
        # 获取允许的工具列表（用于显示约束）
        allowed_tools = self._get_allowed_tools()
        tools_display = ", ".join(allowed_tools) if allowed_tools else "无"

        # 基础角色和领域知识
        prompt = f"""# 角色定位
你是 {self.name}，专门负责{self.config.description}。

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

"""

        # 注入上下文信息
        if context.reg_id:
            prompt += f"""## 当前执行上下文
默认规程: {context.reg_id}
"""

        if context.chapter_scope:
            prompt += f"章节范围限制: {context.chapter_scope}\n"

        if context.hints:
            hints_lines = [f"- {k}: {v}" for k, v in context.hints.items()]
            hints_str = "\n".join(hints_lines)
            prompt += f"""
## 查询提示信息
{hints_str}
"""

        return prompt

    def _build_options(self, context: SubagentContext) -> ClaudeAgentOptions:
        """构建 Agent 选项

        根据 use_preset 配置决定使用 preset: "claude_code" 还是手动提示词。

        Args:
            context: Subagent 上下文

        Returns:
            ClaudeAgentOptions
        """
        # 禁用内置工具（避免与MCP工具冲突）
        disallowed = [
            "Bash", "Read", "Write", "Edit", "Glob", "Grep",
            "LS", "MultiEdit", "NotebookEdit", "NotebookRead",
            "TodoRead", "TodoWrite", "WebFetch", "WebSearch",
        ]

        # 基础选项
        options_kwargs = {
            "mcp_servers": self._get_mcp_config(),
            "allowed_tools": self._get_allowed_tools(),
            "disallowed_tools": disallowed,
            "max_turns": context.max_iterations or 5,
            "permission_mode": "bypassPermissions",
            "include_partial_messages": False,  # 简化事件处理
        }

        # 根据配置选择提示词模式
        if self._use_preset:
            # Preset模式：使用 claude_code preset + 精简的领域特定指令
            options_kwargs["preset"] = "claude_code"
            options_kwargs["system_prompt"] = self._build_domain_prompt(context)
            logger.debug(f"[{self.name}] Using preset: 'claude_code' with domain prompt")
        else:
            # 手动模式：使用完整的手动编写提示词
            options_kwargs["system_prompt"] = self._build_system_prompt(context)
            logger.debug(f"[{self.name}] Using manual system prompt")

        # 只有指定模型时才传递
        if self._model:
            options_kwargs["model"] = self._model

        return ClaudeAgentOptions(**options_kwargs)

    async def execute(self, context: SubagentContext) -> SubagentResult:
        """执行 Subagent

        Args:
            context: 执行上下文

        Returns:
            SubagentResult
        """
        self._tool_calls = []
        self._sources = []

        start_time = time.time()
        final_content = ""

        try:
            async with ClaudeSDKClient(options=self._build_options(context)) as client:
                # 发送查询
                await client.query(context.query)

                # 接收响应
                async for event in client.receive_response():
                    await self._process_event(event)

                    # 检查最终结果
                    if ResultMessage is not None and isinstance(event, ResultMessage):
                        if event.result:
                            final_content = event.result
                        break

                # 如果没有通过 ResultMessage 获取
                if not final_content:
                    final_content = self._get_assembled_text()

            duration_ms = (time.time() - start_time) * 1000

            logger.debug(
                f"Subagent '{self.name}' completed: "
                f"tool_calls={len(self._tool_calls)}, "
                f"sources={len(self._sources)}, "
                f"duration={duration_ms:.1f}ms"
            )

            return SubagentResult(
                agent_type=self.config.agent_type,
                success=True,
                content=final_content,
                sources=list(set(self._sources)),
                tool_calls=self._tool_calls.copy(),
                data={},
            )

        except ClaudeSDKError as e:
            logger.error(f"Subagent '{self.name}' error: {e}")
            return SubagentResult(
                agent_type=self.config.agent_type,
                success=False,
                content="",
                sources=list(set(self._sources)),
                tool_calls=self._tool_calls.copy(),
                data={},
                error=str(e),
            )

        except Exception as e:
            logger.exception(f"Subagent '{self.name}' unexpected error: {e}")
            return SubagentResult(
                agent_type=self.config.agent_type,
                success=False,
                content="",
                sources=[],
                tool_calls=[],
                data={},
                error=str(e),
            )

    async def _process_event(self, event: Any) -> None:
        """处理 SDK 事件

        提取工具调用和来源信息。

        Args:
            event: SDK 事件
        """
        import json

        # 处理 AssistantMessage
        if AssistantMessage is not None and isinstance(event, AssistantMessage):
            for block in event.content:
                # ToolUseBlock - 工具调用
                if ToolUseBlock is not None and isinstance(block, ToolUseBlock):
                    tool_name = block.name
                    tool_input = block.input if isinstance(block.input, dict) else {}
                    tool_id = getattr(block, "id", "") or ""

                    self._tool_calls.append({
                        "name": tool_name,
                        "input": tool_input,
                        "tool_id": tool_id,
                    })

                    logger.debug(f"[{self.name}] Tool call: {tool_name}")

                # ToolResultBlock - 工具结果
                elif ToolResultBlock is not None and isinstance(block, ToolResultBlock):
                    content = getattr(block, "content", None)
                    tool_use_id = getattr(block, "tool_use_id", "") or ""

                    # 更新对应的工具调用
                    for tc in reversed(self._tool_calls):
                        if tc.get("tool_id") == tool_use_id:
                            tc["output"] = content
                            break

                    # 提取来源
                    self._extract_sources(content)

        # 处理独立的 ToolResultBlock
        if ToolResultBlock is not None and isinstance(event, ToolResultBlock):
            content = getattr(event, "content", None)
            self._extract_sources(content)

        # 兼容旧格式
        if hasattr(event, "type") and getattr(event, "type", None) == "tool_result":
            content = getattr(event, "content", None)
            if content:
                self._extract_sources(content)

    def _extract_sources(self, result: Any) -> None:
        """从结果中提取来源信息

        Args:
            result: 工具返回结果
        """
        if result is None:
            return

        if isinstance(result, dict):
            if "source" in result and result["source"]:
                self._sources.append(result["source"])
            for key, value in result.items():
                if key != "source":
                    self._extract_sources(value)

        elif isinstance(result, list):
            for item in result:
                self._extract_sources(item)

        elif isinstance(result, str):
            try:
                import json
                parsed = json.loads(result)
                self._extract_sources(parsed)
            except (json.JSONDecodeError, TypeError):
                pass

    def _get_assembled_text(self) -> str:
        """从工具调用结果中组装文本"""
        if not self._tool_calls:
            return ""

        for tool_call in reversed(self._tool_calls):
            output = tool_call.get("output")
            if output:
                if isinstance(output, dict):
                    return output.get("content_markdown", output.get("content", str(output)))
                elif isinstance(output, str):
                    return output

        return ""

    async def reset(self) -> None:
        """重置状态"""
        self._tool_calls = []
        self._sources = []


class SearchSubagent(BaseClaudeSubagent):
    """搜索专家 Subagent"""
    pass


class TableSubagent(BaseClaudeSubagent):
    """表格专家 Subagent"""
    pass


class ReferenceSubagent(BaseClaudeSubagent):
    """引用专家 Subagent"""
    pass


class DiscoverySubagent(BaseClaudeSubagent):
    """发现专家 Subagent"""
    pass


# Subagent 类映射
SUBAGENT_CLASSES: dict[SubagentType, type[BaseClaudeSubagent]] = {
    SubagentType.SEARCH: SearchSubagent,
    SubagentType.TABLE: TableSubagent,
    SubagentType.REFERENCE: ReferenceSubagent,
    SubagentType.DISCOVERY: DiscoverySubagent,
}


def create_claude_subagent(
    config: SubagentConfig,
    model: str,
    mcp_manager: MCPConnectionManager,
    use_preset: bool = True,
) -> BaseClaudeSubagent:
    """创建 Claude Subagent 实例

    工厂函数，根据配置创建相应的 Claude Subagent。

    Args:
        config: Subagent 配置，包含 agent_type、system_prompt、tools 等
        model: Claude 模型名称（如 "claude-sonnet-4-20250514"）
        mcp_manager: MCP 连接管理器，用于工具集成
        use_preset: 是否使用 preset: "claude_code"（默认True）
            - True: 使用 Anthropic 官方最佳实践 + 精简领域提示词（推荐）
            - False: 使用完整手动编写提示词（向后兼容）

    Returns:
        BaseClaudeSubagent: 根据 config.agent_type 创建的具体 Subagent 实例
            - SearchAgent: 文档搜索和导航
            - TableAgent: 表格查询和提取
            - ReferenceAgent: 交叉引用解析
            - DiscoveryAgent: 语义分析（可选）
            - BaseClaudeSubagent: 默认实现（未匹配特定类型时）

    Example:
        >>> from grid_code.subagents.config import SEARCH_AGENT_CONFIG
        >>> from grid_code.agents.mcp_connection import get_mcp_manager
        >>>
        >>> mcp_manager = get_mcp_manager()
        >>> subagent = create_claude_subagent(
        ...     config=SEARCH_AGENT_CONFIG,
        ...     model="claude-sonnet-4-20250514",
        ...     mcp_manager=mcp_manager,
        ...     use_preset=True  # 使用 Anthropic 官方最佳实践
        ... )
        >>> context = SubagentContext(
        ...     query="母线失压如何处理？",
        ...     reg_id="angui_2024",
        ...     max_iterations=5
        ... )
        >>> result = await subagent.execute(context)
        >>> print(result.content)
    """
    subagent_class = SUBAGENT_CLASSES.get(config.agent_type, BaseClaudeSubagent)
    return subagent_class(config, model, mcp_manager, use_preset)
