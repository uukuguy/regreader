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

import json
import uuid
from typing import Any

from loguru import logger
from openai import AsyncOpenAI

from regreader.agents.orchestrated.base import BaseOrchestrator
from regreader.core.config import get_settings
from regreader.orchestration.hierarchy_manager import HierarchyManager
from regreader.subagents.config import SubagentType, get_config


# LLM 规划提示词模板
PLANNING_SYSTEM_PROMPT = """你是一个智能任务规划器，负责将用户的查询分解为原子化子任务。

可用的 L1 原子化子任务：
1. locate_chapters - 定位章节：从规程目录中定位相关章节
2. fetch_content - 获取内容：获取指定章节的完整内容
3. find_tables - 查找表格：查找并提取相关表格数据
4. resolve_references - 解析引用：解析交叉引用和注释
5. semantic_search - 语义搜索：基于语义相似度查找相关内容

你的任务：
1. 分析用户查询的意图
2. 确定需要哪些 L1 子任务来完成查询
3. 返回 JSON 格式的子任务列表

输出格式（JSON）：
{
  "subtasks": [
    {
      "type": "locate_chapters",
      "reason": "需要定位相关章节",
      "params": {"query": "用户查询关键词"}
    }
  ]
}

注意：
- 只返回 JSON，不要其他文字
- 子任务类型必须是上述 5 种之一
- 合理组合子任务，避免冗余
- 优先使用更精确的子任务（如 find_tables 而不是 semantic_search）
"""

# LLM 聚合提示词模板
AGGREGATION_SYSTEM_PROMPT = """你是一个智能结果聚合器，负责将多个子任务的结果整合成连贯的回答。

你的任务：
1. 理解用户的原始查询意图
2. 分析各个子任务的执行结果
3. 将结果整合成连贯、完整的回答
4. 保留重要的来源信息（页码、章节号等）

输出要求：
- 回答要直接、准确、完整
- 保持逻辑连贯，避免简单拼接
- 如果多个子任务结果有重复，去重后呈现
- 如果结果之间有矛盾，指出并说明
- 保留关键的来源信息（如"见第X页"、"表X-X"等）
"""


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

        # 初始化 LLM 客户端
        settings = get_settings()
        self.llm_client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )
        self.llm_model = settings.llm_model_name

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

    async def _plan_subtasks(self, query: str, context_info: str) -> list[dict[str, Any]]:
        """使用 LLM 规划子任务

        基于用户查询和可用的 L1 原子化功能，使用 LLM 进行智能规划。

        Args:
            query: 用户查询
            context_info: 上下文信息（reg_id + hints）

        Returns:
            子任务列表，每个子任务包含 type 和 params
        """
        try:
            # 构建用户提示词
            user_prompt = f"""用户查询：{query}

上下文信息：{context_info}

请分析查询意图，规划需要的 L1 子任务。"""

            # 调用 LLM 进行规划
            response = await self.llm_client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": PLANNING_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,  # 较低温度，保证规划稳定性
                max_tokens=1000,
            )

            # 解析 LLM 返回的 JSON
            content = response.choices[0].message.content
            if not content:
                raise ValueError("LLM returned empty response")

            # 提取 JSON（可能包含 markdown 代码块）
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            planning_result = json.loads(content)
            subtasks_data = planning_result.get("subtasks", [])

            # 转换为内部格式
            subtasks = []
            for subtask_data in subtasks_data:
                subagent_type_str = subtask_data.get("type", "")
                try:
                    subagent_type = SubagentType(subagent_type_str)
                    params = subtask_data.get("params", {})
                    params["reg_id"] = self.reg_id  # 确保包含 reg_id
                    subtasks.append({
                        "type": subagent_type,
                        "params": params,
                        "reason": subtask_data.get("reason", ""),
                    })
                except ValueError:
                    logger.warning(f"Invalid subagent type: {subagent_type_str}")
                    continue

            # 如果 LLM 没有返回任何有效子任务，使用默认策略
            if not subtasks:
                logger.warning("LLM planning returned no valid subtasks, using default")
                subtasks = self._fallback_planning(query)

            logger.info(f"Planned {len(subtasks)} subtasks: {[st['type'].value for st in subtasks]}")
            return subtasks

        except Exception as e:
            logger.error(f"LLM planning failed: {e}, using fallback")
            return self._fallback_planning(query)

    def _fallback_planning(self, query: str) -> list[dict[str, Any]]:
        """回退规划策略（简单规则匹配）

        当 LLM 规划失败时使用。

        Args:
            query: 用户查询

        Returns:
            子任务列表
        """
        subtasks = []
        query_lower = query.lower()

        # 简单的关键词匹配规则
        if any(kw in query_lower for kw in ["章", "节", "目录", "哪些"]):
            subtasks.append({
                "type": SubagentType.LOCATE_CHAPTERS,
                "params": {"query": query, "reg_id": self.reg_id},
                "reason": "查询包含章节相关关键词",
            })

        if any(kw in query_lower for kw in ["表", "表格"]):
            subtasks.append({
                "type": SubagentType.FIND_TABLES,
                "params": {"query": query, "reg_id": self.reg_id},
                "reason": "查询包含表格相关关键词",
            })

        if any(kw in query_lower for kw in ["注", "见", "参照", "参见"]):
            subtasks.append({
                "type": SubagentType.RESOLVE_REFERENCES,
                "params": {"query": query, "reg_id": self.reg_id},
                "reason": "查询包含引用相关关键词",
            })

        # 如果没有匹配到特定任务，使用语义搜索作为默认
        if not subtasks:
            subtasks.append({
                "type": SubagentType.SEMANTIC_SEARCH,
                "params": {"query": query, "reg_id": self.reg_id},
                "reason": "默认使用语义搜索",
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

    async def _aggregate_results(self, subtask_results: list[dict[str, Any]]) -> str:
        """使用 LLM 聚合子任务结果

        将多个 L1 子任务的结果智能聚合成连贯的最终回答。

        Args:
            subtask_results: 子任务结果列表

        Returns:
            聚合后的最终回答
        """
        if not subtask_results:
            return "未找到相关信息。"

        # 如果只有一个子任务结果，直接返回
        if len(subtask_results) == 1:
            return subtask_results[0].get("output", "未找到相关信息。")

        try:
            # 构建子任务结果摘要
            results_summary = []
            for i, result in enumerate(subtask_results, 1):
                subagent_type = result.get("subagent_type", "unknown")
                output = result.get("output", "")
                results_summary.append(f"子任务{i} ({subagent_type}):\n{output}")

            results_text = "\n\n".join(results_summary)

            # 构建用户提示词
            user_prompt = f"""请将以下子任务的执行结果整合成一个连贯的回答：

{results_text}

请生成一个完整、连贯的回答，去除冗余信息，保留关键内容和来源信息。"""

            # 调用 LLM 进行聚合
            response = await self.llm_client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": AGGREGATION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.5,
                max_tokens=2000,
            )

            aggregated_result = response.choices[0].message.content
            if not aggregated_result:
                raise ValueError("LLM returned empty aggregation result")

            logger.info("Successfully aggregated results using LLM")
            return aggregated_result.strip()

        except Exception as e:
            logger.error(f"LLM aggregation failed: {e}, using fallback")
            return self._fallback_aggregation(subtask_results)

    def _fallback_aggregation(self, subtask_results: list[dict[str, Any]]) -> str:
        """回退聚合策略（简单拼接）

        当 LLM 聚合失败时使用。

        Args:
            subtask_results: 子任务结果列表

        Returns:
            聚合后的结果
        """
        aggregated_parts = []
        for result in subtask_results:
            subagent_type = result.get("subagent_type", "unknown")
            output = result.get("output", "")
            aggregated_parts.append(f"【{subagent_type}】\n{output}")

        return "\n\n".join(aggregated_parts)
