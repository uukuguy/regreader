"""RegSearch-Subagent 实现

规程文档检索领域专家，整合以下内部组件：
- SearchAgent: 文档搜索与导航
- TableAgent: 表格处理与提取
- ReferenceAgent: 引用追踪与解析
- DiscoveryAgent: 语义分析（可选）
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from grid_code.infrastructure.file_context import FileContext
from grid_code.subagents.base import BaseSubagent, SubagentContext
from grid_code.subagents.config import REGSEARCH_AGENT_CONFIG, SubagentConfig
from grid_code.subagents.result import SubagentResult

if TYPE_CHECKING:
    from grid_code.mcp.client import MCPClient


class RegSearchSubagent(BaseSubagent):
    """RegSearch-Subagent 规程检索领域专家

    整合搜索、表格、引用、发现功能的领域子代理。
    支持 Bash+FS 范式的文件系统隔离。

    Attributes:
        mcp_client: MCP 客户端（用于调用工具）
        internal_agents: 内部组件子代理字典
    """

    def __init__(
        self,
        config: SubagentConfig | None = None,
        file_context: FileContext | None = None,
        mcp_client: "MCPClient | None" = None,
        use_file_system: bool = False,
        project_root: Path | None = None,
    ):
        """初始化 RegSearch-Subagent

        Args:
            config: 配置（默认使用 REGSEARCH_AGENT_CONFIG）
            file_context: 文件上下文（可选）
            mcp_client: MCP 客户端
            use_file_system: 是否启用文件系统模式
            project_root: 项目根目录（用于文件系统模式）
        """
        # 使用默认配置
        if config is None:
            config = REGSEARCH_AGENT_CONFIG

        # 自动创建 FileContext（如果启用文件系统模式）
        if use_file_system and file_context is None and config.work_dir:
            root = project_root or Path.cwd()
            file_context = FileContext(
                subagent_name=config.agent_type.value,
                base_dir=root / config.work_dir,
                can_read=[root / d for d in config.readable_dirs],
                can_write=[
                    root / config.work_dir / config.scratch_dir,
                    root / config.work_dir / config.logs_dir,
                ],
                project_root=root,
            )

        super().__init__(config, file_context)
        self.mcp_client = mcp_client
        self.internal_agents: dict[str, BaseSubagent] = {}

    @property
    def name(self) -> str:
        """Subagent 标识名"""
        return "regsearch"

    async def execute(self, context: SubagentContext) -> SubagentResult:
        """执行规程检索任务

        工作流程：
        1. 从文件读取任务（如果使用文件系统模式）
        2. 分析查询意图，选择合适的内部组件
        3. 执行搜索、表格处理、引用追踪等操作
        4. 聚合结果
        5. 写入结果文件（如果使用文件系统模式）

        Args:
            context: 执行上下文

        Returns:
            SubagentResult 包含内容、来源、工具调用记录
        """
        self.log(f"开始执行任务: {context.query}")

        # 1. 从文件读取任务（文件系统模式）
        if self.uses_file_system:
            task_content = self.read_task_from_file()
            if task_content:
                self.log(f"从文件读取任务: {len(task_content)} 字符")

        # 2. 执行核心逻辑
        result = await self._execute_core(context)

        # 3. 写入结果文件（文件系统模式）
        if self.uses_file_system:
            self.write_result_to_file(result)
            self.log("结果已写入文件")

        return result

    async def _execute_core(self, context: SubagentContext) -> SubagentResult:
        """执行核心搜索逻辑

        使用 MCP 工具执行规程检索任务。

        Args:
            context: 执行上下文

        Returns:
            SubagentResult
        """
        # 如果没有 MCP 客户端，返回空结果
        if not self.mcp_client:
            return SubagentResult(
                content="MCP 客户端未配置",
                sources=[],
                tool_calls=[],
                success=False,
            )

        # 执行搜索工作流
        results = []
        sources = []

        try:
            # 1. 获取目录结构（如果有 reg_id）
            if context.reg_id:
                toc_result = await self._call_tool(
                    "get_toc",
                    {"reg_id": context.reg_id, "max_level": 2}
                )
                if toc_result:
                    self.log(f"获取目录: {context.reg_id}")

            # 2. 执行智能搜索
            search_params: dict[str, Any] = {
                "query": context.query,
                "limit": 10,
            }
            if context.reg_id:
                search_params["reg_id"] = context.reg_id
            if context.chapter_scope:
                search_params["chapter_scope"] = context.chapter_scope

            search_result = await self._call_tool("smart_search", search_params)
            if search_result:
                results.append(search_result)
                # 提取来源
                extracted = self._extract_sources_from_result(search_result)
                sources.extend(extracted)
                self.log(f"搜索完成，找到 {len(extracted)} 个来源")

            # 3. 读取相关页面（如果有页码提示）
            page_hint = context.hints.get("page_hint")
            if page_hint and context.reg_id:
                page_result = await self._call_tool(
                    "read_page_range",
                    {
                        "reg_id": context.reg_id,
                        "start_page": page_hint,
                        "end_page": page_hint,
                    }
                )
                if page_result:
                    results.append(page_result)

            # 聚合结果
            content = self._aggregate_results(results)

            return SubagentResult(
                content=content,
                sources=sources,
                tool_calls=self._tool_calls,
                success=True,
                metadata={"query": context.query},
            )

        except Exception as e:
            self.log(f"执行错误: {e}")
            return SubagentResult(
                content=f"执行失败: {e}",
                sources=sources,
                tool_calls=self._tool_calls,
                success=False,
            )

    async def _call_tool(self, tool_name: str, params: dict[str, Any]) -> Any:
        """调用 MCP 工具

        Args:
            tool_name: 工具名称
            params: 工具参数

        Returns:
            工具返回结果
        """
        import time

        start = time.perf_counter()
        try:
            result = await self.mcp_client.call_tool(tool_name, params)  # type: ignore
            duration = (time.perf_counter() - start) * 1000
            self._add_tool_call(tool_name, params, result, duration)
            return result
        except Exception as e:
            duration = (time.perf_counter() - start) * 1000
            self._add_tool_call(tool_name, params, {"error": str(e)}, duration)
            raise

    def _aggregate_results(self, results: list[Any]) -> str:
        """聚合多个结果

        Args:
            results: 结果列表

        Returns:
            聚合后的内容字符串
        """
        if not results:
            return "未找到相关内容"

        parts = []
        for result in results:
            if isinstance(result, dict):
                if "content" in result:
                    parts.append(str(result["content"]))
                elif "results" in result:
                    for r in result["results"]:
                        if isinstance(r, dict) and "content" in r:
                            parts.append(str(r["content"]))
            elif isinstance(result, str):
                parts.append(result)

        return "\n\n---\n\n".join(parts) if parts else "未找到相关内容"

    async def reset(self) -> None:
        """重置 Subagent 状态"""
        self._clear_state()
        # 重置内部组件
        for agent in self.internal_agents.values():
            await agent.reset()

    def register_internal_agent(self, name: str, agent: BaseSubagent) -> None:
        """注册内部组件子代理

        Args:
            name: 组件名称（如 'search', 'table'）
            agent: 子代理实例
        """
        self.internal_agents[name] = agent

    def get_internal_agent(self, name: str) -> BaseSubagent | None:
        """获取内部组件子代理

        Args:
            name: 组件名称

        Returns:
            子代理实例，或 None
        """
        return self.internal_agents.get(name)
