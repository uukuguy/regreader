"""OrchestratorAgent - L2 编排智能体

L2 编排智能体，负责理解用户主任务并组合 L1 原子化功能。

核心职责：
1. 理解用户主任务的意图
2. 基于可用的 L1 原子化子任务功能进行规划推理组合
3. 通过 HierarchyManager 调度 L1 子智能体
4. 聚合 L1 子智能体返回的结果

可用工具：
- L1 子任务功能 (locate_chapters, fetch_content, find_tables, resolve_references, semantic_search)
- Bash+FS 基础工具 (file operations, etc.)
"""

import uuid
from typing import Any

from loguru import logger

from regreader.agents.orchestrated.base import BaseOrchestrator
from regreader.orchestration.hierarchy_manager import HierarchyManager
from regreader.subagents.config import SubagentType, get_config


class OrchestratorAgent(BaseOrchestrator):
    """L2 编排智能体

    统一的编排智能体实现，支持三个框架（Claude SDK/Pydantic AI/LangGraph）。

    架构层级：
    - L2: OrchestratorAgent（本类）- 理解主任务，组合 L1 功能
    - L1: 原子化子任务（locate_chapters, fetch_content, etc.）
    - L0: MCP 工具（get_toc, smart_search, etc.）

    Attributes:
        hierarchy_manager: Agent 调用栈管理器
        agent_id: 当前 agent 的唯一标识
        available_l1_subagents: 可用的 L1 子任务类型列表
    """

    def __init__(
        self,
        reg_id: str | None = None,
        use_coordinator: bool = False,
        callback: Any = None,
        session_id: str | None = None,
    ):
        """初始化 OrchestratorAgent

        Args:
            reg_id: 默认规程ID
            use_coordinator: 是否使用 Coordinator（Bash+FS 模式）
            callback: 状态回调
            session_id: 会话ID（用于 HierarchyManager）
        """
        super().__init__(reg_id, use_coordinator, callback)

        # 初始化 HierarchyManager
        self.hierarchy_manager = HierarchyManager(session_id)

        # 生成 agent ID
        self.agent_id = f"orch_{uuid.uuid4().hex[:8]}"

        # 可用的 L1 子任务类型
        self.available_l1_subagents = [
            SubagentType.LOCATE_CHAPTERS,
            SubagentType.FETCH_CONTENT,
            SubagentType.FIND_TABLES,
            SubagentType.RESOLVE_REFERENCES,
            SubagentType.SEMANTIC_SEARCH,
        ]

        logger.info(f"OrchestratorAgent initialized with ID: {self.agent_id}")

    @property
    def name(self) -> str:
        """Agent 名称"""
        return "OrchestratorAgent"

    async def _ensure_initialized(self) -> None:
        """初始化组件（框架特定）

        OrchestratorAgent 的初始化包括：
        1. 注册自身到 HierarchyManager
        2. 验证 L1 子任务配置
        3. 保存初始状态
        """
        if self._initialized:
            return

        # 注册自身到 HierarchyManager
        self.hierarchy_manager.push_agent(
            agent_id=self.agent_id,
            agent_name=self.name,
            parent_id=None,  # L2 编排智能体没有父级
            level=2,
            user_input="",  # 初始化时没有用户输入
        )

        # 验证 L1 子任务配置
        for subagent_type in self.available_l1_subagents:
            try:
                config = get_config(subagent_type)
                logger.debug(f"L1 subagent {subagent_type.value} config loaded: {config.name}")
            except KeyError:
                logger.warning(f"L1 subagent {subagent_type.value} config not found")

        # 保存初始状态
        self.hierarchy_manager.save_state()

        self._initialized = True
        logger.info(f"{self.name} initialized successfully")

    async def _execute_orchestration(
        self,
        query: str,
        context_info: str,
    ) -> str:
        """执行编排逻辑

        L2 编排智能体的核心逻辑：
        1. 更新 agent 状态为 "thinking"
        2. 分析用户查询，确定需要哪些 L1 子任务
        3. 调度 L1 子智能体执行子任务
        4. 聚合子任务结果
        5. 生成最终回答

        Args:
            query: 用户查询
            context_info: 上下文信息（reg_id + hints）

        Returns:
            最终回答内容

        Raises:
            Exception: 执行过程中的任何异常
        """
        # 1. 更新状态为 thinking
        self.hierarchy_manager.update_agent_status(
            agent_id=self.agent_id,
            status="thinking",
            thinking=f"正在分析查询: {query}",
        )
        self.hierarchy_manager.save_state()

        logger.info(f"OrchestratorAgent executing query: {query}")

        # 2. 分析查询，确定需要的 L1 子任务
        # TODO: 这里需要 LLM 进行规划推理，确定需要调用哪些 L1 子任务
        # 当前先使用简单的规则匹配作为占位符
        subtasks = self._plan_subtasks(query, context_info)

        logger.debug(f"Planned subtasks: {[st['type'].value for st in subtasks]}")

        # 3. 调度 L1 子智能体执行子任务
        subtask_results = []
        for subtask in subtasks:
            result = await self._execute_subtask(subtask)
            subtask_results.append(result)

        # 4. 聚合子任务结果
        aggregated_result = self._aggregate_results(subtask_results)

        # 5. 更新状态为 completed
        self.hierarchy_manager.update_agent_status(
            agent_id=self.agent_id,
            status="completed",
            output=aggregated_result,
        )
        self.hierarchy_manager.save_state()

        logger.info(f"OrchestratorAgent completed query execution")
        return aggregated_result

    def _plan_subtasks(self, query: str, context_info: str) -> list[dict[str, Any]]:
        """规划子任务（占位符实现）

        TODO: 这里需要 LLM 进行规划推理，基于可用的 L1 原子化功能进行组合。
        当前使用简单的规则匹配作为占位符。

        Args:
            query: 用户查询
            context_info: 上下文信息

        Returns:
            子任务列表，每个子任务包含 type 和 params
        """
        subtasks = []

        # 简单的关键词匹配规则（占位符）
        query_lower = query.lower()

        # 如果查询包含章节相关关键词，添加 LOCATE_CHAPTERS 任务
        if any(kw in query_lower for kw in ["章", "节", "目录", "哪些"]):
            subtasks.append({
                "type": SubagentType.LOCATE_CHAPTERS,
                "params": {"query": query, "reg_id": self.reg_id},
            })

        # 如果查询包含表格相关关键词，添加 FIND_TABLES 任务
        if any(kw in query_lower for kw in ["表", "表格"]):
            subtasks.append({
                "type": SubagentType.FIND_TABLES,
                "params": {"query": query, "reg_id": self.reg_id},
            })

        # 如果查询包含引用相关关键词，添加 RESOLVE_REFERENCES 任务
        if any(kw in query_lower for kw in ["注", "见", "参照", "参见"]):
            subtasks.append({
                "type": SubagentType.RESOLVE_REFERENCES,
                "params": {"query": query, "reg_id": self.reg_id},
            })

        # 如果没有匹配到特定任务，使用语义搜索作为默认
        if not subtasks:
            subtasks.append({
                "type": SubagentType.SEMANTIC_SEARCH,
                "params": {"query": query, "reg_id": self.reg_id},
            })

        return subtasks

    async def _execute_subtask(self, subtask: dict[str, Any]) -> dict[str, Any]:
        """执行单个子任务

        TODO: 这里需要实际调用 L1 子智能体执行子任务。
        当前返回占位符结果。

        Args:
            subtask: 子任务定义（包含 type 和 params）

        Returns:
            子任务执行结果
        """
        subagent_type = subtask["type"]
        params = subtask["params"]

        # 生成子智能体 ID
        subagent_id = f"{subagent_type.value}_{uuid.uuid4().hex[:8]}"

        # 注册子智能体到 HierarchyManager
        self.hierarchy_manager.push_agent(
            agent_id=subagent_id,
            agent_name=subagent_type.value,
            parent_id=self.agent_id,
            level=1,
            user_input=params.get("query", ""),
        )

        logger.info(f"Executing L1 subtask: {subagent_type.value}")

        # TODO: 实际调用 L1 子智能体
        # 当前返回占位符结果
        result = {
            "subagent_type": subagent_type.value,
            "status": "completed",
            "output": f"[占位符] {subagent_type.value} 执行结果",
        }

        # 更新子智能体状态
        self.hierarchy_manager.update_agent_status(
            agent_id=subagent_id,
            status="completed",
            output=result["output"],
        )

        # 从栈中移除子智能体
        self.hierarchy_manager.pop_agent(subagent_id)
        self.hierarchy_manager.save_state()

        return result

    def _aggregate_results(self, subtask_results: list[dict[str, Any]]) -> str:
        """聚合子任务结果

        将多个 L1 子任务的结果聚合成最终回答。

        Args:
            subtask_results: 子任务结果列表

        Returns:
            聚合后的最终回答
        """
        if not subtask_results:
            return "未找到相关信息。"

        # 简单的结果拼接（占位符实现）
        # TODO: 这里需要 LLM 进行智能聚合，生成连贯的回答
        aggregated_parts = []
        for result in subtask_results:
            subagent_type = result.get("subagent_type", "unknown")
            output = result.get("output", "")
            aggregated_parts.append(f"【{subagent_type}】\n{output}")

        return "\n\n".join(aggregated_parts)
