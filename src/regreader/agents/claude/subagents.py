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

from regreader.agents.shared.mcp_config import get_tool_name
from regreader.agents.shared.mcp_connection import MCPConnectionManager
from regreader.subagents.base import BaseSubagent, SubagentContext
from regreader.subagents.config import SubagentConfig, SubagentType
from regreader.orchestration.result import SubagentResult

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
        UserMessage,
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
    UserMessage = None  # type: ignore
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
            # SystemPromptPreset TypedDict 结构
            options_kwargs["system_prompt"] = {
                "type": "preset",
                "preset": "claude_code",
                "append": self._build_domain_prompt(context),
            }
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
                            logger.debug(
                                f"[{self.name}] Got ResultMessage with content "
                                f"length={len(final_content)}"
                            )
                        else:
                            logger.debug(f"[{self.name}] Got empty ResultMessage")
                        break

                # 如果没有通过 ResultMessage 获取
                if not final_content:
                    final_content = self._get_assembled_text()
                    logger.debug(
                        f"[{self.name}] Assembled text from tool calls: "
                        f"length={len(final_content)}, tool_calls={len(self._tool_calls)}"
                    )

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

        # 记录事件类型用于调试
        event_type = type(event).__name__
        logger.debug(f"[{self.name}] Processing event: {event_type}")

        # 优先处理独立的 ToolResultBlock（Claude SDK 可能直接发送）
        if ToolResultBlock is not None and isinstance(event, ToolResultBlock):
            content = getattr(event, "content", None)
            tool_use_id = getattr(event, "tool_use_id", "") or ""

            logger.debug(
                f"[{self.name}] Standalone ToolResultBlock: tool_use_id={tool_use_id}, "
                f"has_content={content is not None}, "
                f"content_type={type(content).__name__ if content else 'None'}"
            )

            # 更新对应的工具调用
            found = False
            for tc in reversed(self._tool_calls):
                if tc.get("tool_id") == tool_use_id:
                    tc["output"] = content
                    found = True
                    logger.debug(
                        f"[{self.name}] Updated tool call output for {tc.get('name')} "
                        f"(standalone ToolResultBlock)"
                    )
                    break

            if not found:
                logger.warning(
                    f"[{self.name}] Could not find matching tool call for "
                    f"tool_use_id={tool_use_id} (standalone ToolResultBlock)"
                )

            # 提取来源
            self._extract_sources(content)
            return  # 已处理，直接返回

        # 处理 AssistantMessage
        if AssistantMessage is not None and isinstance(event, AssistantMessage):
            for block in event.content:
                block_type = type(block).__name__
                logger.debug(f"[{self.name}]   Block in AssistantMessage: {block_type}")

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

                # ToolResultBlock - 工具结果（嵌入在 AssistantMessage 中）
                elif ToolResultBlock is not None and isinstance(block, ToolResultBlock):
                    content = getattr(block, "content", None)
                    tool_use_id = getattr(block, "tool_use_id", "") or ""

                    logger.debug(
                        f"[{self.name}] ToolResultBlock in AssistantMessage: "
                        f"tool_use_id={tool_use_id}, has_content={content is not None}, "
                        f"content_type={type(content).__name__ if content else 'None'}"
                    )

                    # 更新对应的工具调用
                    found = False
                    for tc in reversed(self._tool_calls):
                        if tc.get("tool_id") == tool_use_id:
                            tc["output"] = content
                            found = True
                            logger.debug(
                                f"[{self.name}] Updated tool call output for {tc.get('name')} "
                                f"(embedded ToolResultBlock)"
                            )
                            break

                    if not found:
                        logger.warning(
                            f"[{self.name}] Could not find matching tool call for "
                            f"tool_use_id={tool_use_id} (embedded ToolResultBlock)"
                        )

                    # 提取来源
                    self._extract_sources(content)

        # 处理 UserMessage（包含工具调用结果）
        if UserMessage is not None and isinstance(event, UserMessage):
            for block in event.content:
                block_type = type(block).__name__
                logger.debug(f"[{self.name}]   Block in UserMessage: {block_type}")

                # ToolResultBlock - 工具结果
                if ToolResultBlock is not None and isinstance(block, ToolResultBlock):
                    content = getattr(block, "content", None)
                    tool_use_id = getattr(block, "tool_use_id", "") or ""

                    logger.debug(
                        f"[{self.name}] ToolResultBlock in UserMessage: "
                        f"tool_use_id={tool_use_id}, has_content={content is not None}, "
                        f"content_type={type(content).__name__ if content else 'None'}"
                    )

                    # 更新对应的工具调用
                    found = False
                    for tc in reversed(self._tool_calls):
                        if tc.get("tool_id") == tool_use_id:
                            tc["output"] = content
                            found = True
                            logger.debug(
                                f"[{self.name}] Updated tool call output for {tc.get('name')} "
                                f"(from UserMessage)"
                            )
                            break

                    if not found:
                        logger.warning(
                            f"[{self.name}] Could not find matching tool call for "
                            f"tool_use_id={tool_use_id} (from UserMessage)"
                        )

                    # 提取来源
                    self._extract_sources(content)

        # 兼容旧格式
        if hasattr(event, "type") and getattr(event, "type", None) == "tool_result":
            content = getattr(event, "content", None)
            if content:
                logger.debug(f"[{self.name}] Legacy tool_result event")
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
        import json

        if not self._tool_calls:
            logger.debug(f"[{self.name}] No tool calls to assemble text from")
            return ""

        logger.debug(
            f"[{self.name}] Attempting to assemble text from {len(self._tool_calls)} tool calls"
        )

        for i, tool_call in enumerate(reversed(self._tool_calls)):
            output = tool_call.get("output")
            tool_name = tool_call.get("name", "unknown")

            logger.debug(
                f"[{self.name}] Tool call #{len(self._tool_calls)-i}: "
                f"name={tool_name}, has_output={output is not None}, "
                f"output_type={type(output).__name__ if output else 'None'}"
            )

            if output:
                if isinstance(output, dict):
                    content = output.get("content_markdown", output.get("content", str(output)))
                    logger.debug(
                        f"[{self.name}] Extracted content from dict output: "
                        f"length={len(content)}"
                    )
                    return content
                elif isinstance(output, str):
                    # 尝试检测是否为原始JSON（agent未能正确格式化）
                    if self._is_raw_json(output):
                        logger.warning(
                            f"[{self.name}] Detected raw JSON output from agent, "
                            f"attempting fallback formatting"
                        )
                        formatted = self._format_json_fallback(output, tool_name)
                        if formatted:
                            return formatted

                    logger.debug(
                        f"[{self.name}] Using string output directly: length={len(output)}"
                    )
                    return output

        logger.warning(f"[{self.name}] No valid content found in any tool call output")
        return ""

    def _is_raw_json(self, text: str) -> bool:
        """检测文本是否为原始JSON输出

        Args:
            text: 待检测的文本

        Returns:
            是否为原始JSON
        """
        import json

        # 去掉前后空白
        text = text.strip()

        # 基本的JSON检测：以 { 或 [ 开头，且包含 "result" 等关键字
        if not (text.startswith("{") or text.startswith("[")):
            return False

        try:
            # 尝试解析为JSON
            json.loads(text)
            # 检查是否包含典型的工具输出关键字
            has_tool_keys = any(
                key in text for key in ['"result":', '"sources":', '"snippet":']
            )
            return has_tool_keys
        except json.JSONDecodeError:
            return False

    def _format_json_fallback(self, json_text: str, tool_name: str) -> str:
        """格式化原始JSON为可读文本（回退方案）

        当agent未能正确格式化工具输出时，此方法提供基本的格式化支持。

        Args:
            json_text: 原始JSON文本
            tool_name: 工具名称

        Returns:
            格式化后的文本，如果无法格式化则返回空字符串
        """
        import json

        try:
            data = json.loads(json_text)

            # 处理 smart_search 工具输出
            if tool_name == "mcp__gridcode__smart_search" and isinstance(data, dict):
                results = data.get("result", [])
                if not results:
                    return "未找到相关内容。"

                # 格式化搜索结果
                lines = ["根据搜索结果，找到以下相关内容：\n"]

                for idx, result in enumerate(results[:5], 1):  # 只显示前5条
                    snippet = result.get("snippet", "")
                    source = result.get("source", "")
                    chapter_path = result.get("chapter_path", [])

                    # 提取章节信息
                    chapter = " > ".join(chapter_path) if chapter_path else "未知章节"

                    lines.append(f"**{idx}. {chapter}**")
                    lines.append(f"   {snippet}")
                    lines.append(f"   来源：{source}\n")

                if len(results) > 5:
                    lines.append(f"...以及其他 {len(results)-5} 条结果")

                return "\n".join(lines)

            # 处理 search_tables 工具输出
            elif tool_name == "mcp__gridcode__search_tables" and isinstance(data, dict):
                results = data.get("result", [])
                if not results:
                    return "未找到相关表格。"

                lines = ["找到以下相关表格：\n"]

                for idx, table in enumerate(results[:3], 1):
                    table_id = table.get("table_id", "")
                    source = table.get("source", "")

                    lines.append(f"**表格 {idx}**: {table_id}")
                    lines.append(f"   来源：{source}\n")

                lines.append("\n请使用 get_table_by_id 工具获取表格详细内容。")

                return "\n".join(lines)

            # 其他情况：提供通用格式化
            else:
                logger.debug(f"[{self.name}] No specific formatter for tool: {tool_name}")
                return f"工具 {tool_name} 返回了结果，但格式需要agent处理。原始数据长度：{len(json_text)} 字符。"

        except Exception as e:
            logger.error(f"[{self.name}] Failed to format JSON fallback: {e}")
            return ""

    async def reset(self) -> None:
        """重置状态"""
        self._tool_calls = []
        self._sources = []


class SearchSubagent(BaseClaudeSubagent):
    """搜索专家 Subagent"""

    @property
    def name(self) -> str:
        """Subagent 标识名"""
        return "search"


class TableSubagent(BaseClaudeSubagent):
    """表格专家 Subagent"""

    @property
    def name(self) -> str:
        """Subagent 标识名"""
        return "table"


class ReferenceSubagent(BaseClaudeSubagent):
    """引用专家 Subagent"""

    @property
    def name(self) -> str:
        """Subagent 标识名"""
        return "reference"


class DiscoverySubagent(BaseClaudeSubagent):
    """发现专家 Subagent"""

    @property
    def name(self) -> str:
        """Subagent 标识名"""
        return "discovery"


class ClaudeRegSearchSubagent(BaseClaudeSubagent):
    """RegSearch 领域专家 Subagent

    整合搜索、表格、引用、发现功能的 Claude 实现。
    作为领域子代理，拥有所有 MCP 工具的访问权限。
    """

    @property
    def name(self) -> str:
        """Subagent 标识名"""
        return "regsearch"


# Subagent 类映射
SUBAGENT_CLASSES: dict[SubagentType, type[BaseClaudeSubagent]] = {
    # 领域子代理
    SubagentType.REGSEARCH: ClaudeRegSearchSubagent,
    # 内部组件子代理
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
        >>> from regreader.subagents.config import SEARCH_AGENT_CONFIG
        >>> from regreader.agents.mcp_connection import get_mcp_manager
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
