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

import asyncio
import json
import time
import uuid
from typing import Any

from loguru import logger
from openai import AsyncOpenAI

from regreader.agents.orchestrated.base import BaseOrchestrator
from regreader.agents.shared.events import (
    phase_change_event,
    tool_start_event,
    tool_end_event,
)
from regreader.core.config import get_settings
from regreader.observability import get_logger, get_metrics_collector, get_tracer
from regreader.observability.logging import set_trace_id
from regreader.observability.tracer import NodeType, NodeStatus
from regreader.orchestration.hierarchy_manager import HierarchyManager
from regreader.subagents.config import SubagentType, get_config


# LLM 规划提示词模板
PLANNING_SYSTEM_PROMPT = """你是一个智能任务规划器，负责将用户的查询分解为原子化子任务。

**核心原则：规划必须能够回答用户的问题**

可用的 L1 原子化子任务：
0. locate_regulations - 定位规程：根据查询自动定位相关规程（当未指定规程ID时必须首先调用）
1. locate_chapters - 定位章节：从规程目录中定位相关章节
2. fetch_content - 获取内容：获取指定章节的完整内容
3. find_tables - 查找表格：查找并提取相关表格数据
4. resolve_references - 解析引用：解析交叉引用和注释
5. semantic_search - 语义搜索：基于语义相似度查找相关内容

**系统化工作流规则（必须遵守）**：
1. 如果没有 reg_id → 必须首先使用 locate_regulations
2. 如果需要章节内容 → 必须先使用 locate_chapters 验证章节存在，再使用 fetch_content
3. 如果需要表格 → 必须使用 find_tables 查找，不要假设表格编号
4. 如果需要引用内容 → 必须使用 resolve_references 解析，不要猜测
5. 禁止假设：所有信息必须通过工具验证

子任务依赖关系：
1. 如果没有 reg_id: 所有子任务必须在 locate_regulations 之后执行
2. fetch_content 必须在 locate_chapters 之后执行
3. resolve_references 必须在 locate_chapters 之后执行
4. 其他子任务（find_tables, semantic_search）可以并行执行

你的任务：
1. **深入分析用户查询的意图**：理解用户真正想要什么信息
2. **验证规划能否回答问题**：在规划完成后，问自己"这些子任务的结果能回答用户的问题吗？"
3. **重要**：如果用户查询中没有明确指定规程ID，必须首先添加 locate_regulations 子任务
4. 确定需要哪些 L1 子任务来完成查询
5. **为每个子任务提供详细的理由说明**：
   - 为什么需要这个子任务？
   - 这个子任务要查找什么具体信息？
   - 预期从这个子任务获得什么结果？
   - 这个结果如何帮助回答用户的问题？
6. 考虑依赖关系，合理安排子任务顺序
7. 返回 JSON 格式的子任务列表

输出格式（JSON）：
{
  "reasoning": "详细的整体规划思路，包括：
    1. 用户查询的核心意图是什么
    2. 为什么选择这些子任务
    3. 这些子任务如何协同工作以回答用户问题
    4. 预期的信息流向和最终输出
    5. **验证**：这些子任务的结果能否完整回答用户的问题？如果不能，还需要什么？",
  "subtasks": [
    {
      "type": "locate_regulations",
      "reason": "用户查询中提到了'安控'和'稳规'关键词，需要定位相关的规程文件（预期找到 angui_2024 和 wengui_2024）",
      "expected_output": "找到相关规程的ID和基本信息",
      "params": {"query": "用户查询关键词"}
    },
    {
      "type": "find_tables",
      "reason": "安控系统的装置配置通常以表格形式呈现，需要查找锦苏安控系统的配置表以了解系统结构",
      "expected_output": "锦苏安控系统的装置配置表，包括厂站、装置型号、调度命名等信息",
      "params": {"query": "锦苏安控 装置配置"}
    }
  ]
}

注意：
- 只返回 JSON，不要其他文字
- 子任务类型必须是上述 6 种之一
- **如果用户查询中没有明确的规程ID（如 'angui_2024'），必须首先添加 locate_regulations 子任务**
- 合理组合子任务，避免冗余
- 优先使用更精确的子任务（如 find_tables 而不是 semantic_search）
- **reason 和 expected_output 字段必须详细、具体，让用户能够理解每个子任务的作用**
- **在 reasoning 中必须包含验证步骤：这些子任务能否回答用户的问题**
"""

# LLM 聚合提示词模板
AGGREGATION_SYSTEM_PROMPT = """你是一个智能结果聚合器，负责将多个子任务的结果整合成连贯的回答。

**核心原则：直接回答用户的原始问题**

你的任务：
1. **理解用户的原始查询意图**：用户真正想知道什么？
2. **验证结果是否回答了问题**：这些子任务结果是否包含答案？
3. 分析各个子任务的执行结果
4. 将结果整合成连贯、完整的回答
5. 保留重要的来源信息（页码、章节号等）

**回答策略**：
- 如果结果中包含答案 → 直接提取并整合，回答用户问题
- 如果结果不完整 → 明确指出缺少什么信息，建议用户如何补充查询
- 如果结果不相关 → 诚实说明"未找到相关信息"，不要编造

输出要求：
- **直接回答用户的问题**，不要泛泛而谈或提供无关信息
- 回答要准确、完整、具体
- 保持逻辑连贯，避免简单拼接
- 如果多个子任务结果有重复，去重后呈现
- 如果结果之间有矛盾，指出并说明
- 保留关键的来源信息（如"见第X页"、"表X-X"等）
- **如果无法回答问题，明确说明原因和缺失的信息**
"""

# 子任务依赖关系定义（保留作为回退）
# 格式：{子任务类型: [依赖的子任务类型列表]}
SUBTASK_DEPENDENCIES = {
    SubagentType.FETCH_CONTENT: [SubagentType.LOCATE_CHAPTERS],
    SubagentType.RESOLVE_REFERENCES: [SubagentType.LOCATE_CHAPTERS],
    # 其他子任务没有依赖关系，可以并行执行
}


def get_subtask_dependencies(
    subtask_type: SubagentType,
    has_reg_id: bool
) -> list[SubagentType]:
    """动态获取子任务依赖关系

    Args:
        subtask_type: 子任务类型
        has_reg_id: 是否已有 reg_id

    Returns:
        依赖的子任务类型列表
    """
    # 基础依赖关系
    base_deps = SUBTASK_DEPENDENCIES.get(subtask_type, [])

    # 如果没有 reg_id，所有子任务都依赖 LOCATE_REGULATIONS
    if not has_reg_id and subtask_type != SubagentType.LOCATE_REGULATIONS:
        deps = [SubagentType.LOCATE_REGULATIONS] + base_deps
    else:
        deps = base_deps

    return deps


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
        parallel_mode: bool = False,
    ):
        """初始化 OrchestratorAgent

        Args:
            reg_id: 默认规程ID
            use_coordinator: 是否使用 Coordinator（Bash+FS 模式）
            callback: 状态回调
            session_id: 会话ID（用于 HierarchyManager）
            parallel_mode: 是否启用并行执行模式（默认 False）
        """
        super().__init__(reg_id, use_coordinator, callback)

        # 初始化 HierarchyManager
        self.hierarchy_manager = HierarchyManager(session_id)

        # 生成 agent ID
        self.agent_id = f"orch_{uuid.uuid4().hex[:8]}"

        # 并行执行模式
        self.parallel_mode = parallel_mode

        # 执行锁：防止并行执行时的竞态条件
        self._reg_id_lock = asyncio.Lock()

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

        # 验证 LLM 配置
        if not self.llm_model:
            logger.warning(
                "LLM model name is empty! Check REGREADER_LLM_MODEL_NAME or OPENAI_MODEL_NAME environment variable"
            )
        if not settings.llm_api_key:
            logger.warning("LLM API key is empty! Check REGREADER_LLM_API_KEY or OPENAI_API_KEY environment variable")

        logger.debug(
            f"LLM configuration: model={self.llm_model}, "
            f"base_url={settings.llm_base_url}, "
            f"api_key={'***' if settings.llm_api_key else 'NOT SET'}"
        )

        # 初始化监控组件
        self.metrics = get_metrics_collector()
        self.tracer = get_tracer()
        self.obs_logger = get_logger()

        # 初始化 MCP 客户端（用于调用 L0 工具）
        self._mcp_client = None  # 延迟初始化

        logger.info(
            f"OrchestratorAgent initialized with ID: {self.agent_id}, "
            f"parallel_mode: {parallel_mode}"
        )

    @property
    def name(self) -> str:
        """Agent 名称"""
        return "OrchestratorAgent"

    async def _ensure_initialized(self) -> None:
        """初始化组件（框架特定）

        OrchestratorAgent 的初始化包括：
        1. 注册自身到 HierarchyManager
        2. 验证 L1 子任务配置
        3. 初始化 MCP 客户端
        4. 保存初始状态
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

        # 初始化 MCP 客户端
        await self._init_mcp_client()

        # 保存初始状态
        self.hierarchy_manager.save_state()

        self._initialized = True
        logger.info(f"{self.name} initialized successfully")

    async def _init_mcp_client(self) -> None:
        """初始化 MCP 客户端

        使用全局 MCPConnectionManager 以复用命令行配置的 MCP 连接。
        """
        if self._mcp_client is not None:
            return

        from regreader.agents.shared.mcp_connection import get_mcp_manager

        # 使用全局 MCP 连接管理器（会使用命令行传递的配置）
        mcp_manager = get_mcp_manager()
        self._mcp_client = await mcp_manager.get_client()
        logger.debug("MCP client initialized using global connection manager")

    async def _get_mcp_client(self):
        """获取 MCP 客户端（确保已初始化）"""
        if self._mcp_client is None:
            await self._init_mcp_client()
        return self._mcp_client

    async def cleanup(self) -> None:
        """清理资源

        关闭 MCP 客户端连接，释放资源。
        """
        if self._mcp_client is not None:
            try:
                await self._mcp_client.disconnect()
                logger.debug("MCP client disconnected")
            except Exception as e:
                logger.warning(f"Error disconnecting MCP client: {e}")
            finally:
                self._mcp_client = None
                self._connected = False

    async def close(self) -> None:
        """关闭 Agent（cleanup 的别名）

        提供与其他 Agent 一致的接口。
        """
        await self.cleanup()

    async def __aenter__(self) -> "OrchestratorAgent":
        """异步上下文管理器入口"""
        await self._ensure_initialized()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        await self.cleanup()

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
        # 设置 trace_id 并记录查询开始
        trace_id = set_trace_id()
        start_time = time.time()

        self.obs_logger.info(
            "Query started",
            query=query,
            context_info=context_info,
            parallel_mode=self.parallel_mode,
        )

        # 创建查询追踪节点
        query_node_id = f"query_{self.agent_id}"
        self.tracer.add_node(query_node_id, NodeType.QUERY, query[:50])
        self.tracer.start_node(query_node_id)

        # 1. 更新状态为 thinking
        self.hierarchy_manager.update_agent_status(
            agent_id=self.agent_id,
            status="thinking",
            thinking=f"正在分析查询: {query}",
        )
        self.hierarchy_manager.save_state()

        logger.info(f"OrchestratorAgent executing query: {query}")

        # 2. 分析查询，确定需要的 L1 子任务
        plan_node_id = f"plan_{self.agent_id}"
        self.tracer.add_node(plan_node_id, NodeType.PLAN, "任务规划", parent_id=query_node_id)
        self.tracer.start_node(plan_node_id)

        plan_start = time.time()
        subtasks = await self._plan_subtasks(query, context_info)
        plan_elapsed = time.time() - plan_start

        self.tracer.complete_node(plan_node_id, NodeStatus.SUCCESS)
        self.obs_logger.info(
            "Planning completed",
            subtask_count=len(subtasks),
            subtask_types=[st['type'].value for st in subtasks],
            plan_time=plan_elapsed,
        )

        logger.debug(f"Planned subtasks: {[st['type'].value for st in subtasks]}")

        # 构建规划推理信息
        reasoning_lines = []
        for i, st in enumerate(subtasks, 1):
            subagent_type = st['type'].value
            reason = st.get('reason', '无说明')
            params_summary = ', '.join([f"{k}={v}" for k, v in st['params'].items() if k != 'reg_id'])
            reasoning_lines.append(f"{i}. {subagent_type}: {reason}")
            if params_summary:
                reasoning_lines.append(f"   参数: {params_summary}")

        reasoning_text = "\n".join(reasoning_lines)

        # 发送规划完成事件（包含推理过程）
        await self._send_event(phase_change_event(
            "planning",
            f"📋 规划推理:\n{reasoning_text}\n\n"
            f"✓ 已规划 {len(subtasks)} 个子任务"
        ))

        # 保存子任务数量（用于基准测试）
        self._last_subtask_count = len(subtasks)

        # 3. 调度 L1 子智能体执行子任务
        exec_start = time.time()
        if self.parallel_mode:
            # 并行执行模式：根据依赖关系分批并行执行
            subtask_results = await self._execute_subtasks_parallel(subtasks)
        else:
            # 顺序执行模式：逐个执行子任务
            subtask_results = await self._execute_subtasks_sequential(subtasks)
        exec_elapsed = time.time() - exec_start

        self.obs_logger.info(
            "Subtasks execution completed",
            execution_time=exec_elapsed,
            parallel_mode=self.parallel_mode,
        )

        # 4. 聚合子任务结果
        agg_node_id = f"aggregate_{self.agent_id}"
        self.tracer.add_node(agg_node_id, NodeType.AGGREGATE, "结果聚合", parent_id=query_node_id)
        self.tracer.start_node(agg_node_id)

        agg_start = time.time()
        aggregated_result = await self._aggregate_results(subtask_results, query)
        agg_elapsed = time.time() - agg_start

        self.tracer.complete_node(agg_node_id, NodeStatus.SUCCESS)

        # 发送聚合完成事件
        await self._send_event(phase_change_event(
            "aggregation",
            f"结果聚合完成，耗时 {agg_elapsed:.2f}s"
        ))

        # 5. 更新状态为 completed
        self.hierarchy_manager.update_agent_status(
            agent_id=self.agent_id,
            status="completed",
            output=aggregated_result,
        )
        self.hierarchy_manager.save_state()

        # 记录总体查询指标
        total_elapsed = time.time() - start_time
        self.metrics.record_query_latency(
            total_elapsed,
            labels={
                "agent_type": "orchestrator",
                "parallel_mode": str(self.parallel_mode),
                "subtask_count": str(len(subtasks)),
            }
        )

        # 完成查询追踪
        self.tracer.complete_node(query_node_id, NodeStatus.SUCCESS)

        self.obs_logger.info(
            "Query completed",
            total_time=total_elapsed,
            plan_time=plan_elapsed,
            execution_time=exec_elapsed,
            aggregation_time=agg_elapsed,
        )

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
            # 明确指出是否有 reg_id，帮助 LLM 正确规划
            has_reg_id = self.reg_id is not None
            reg_id_hint = f"已指定规程ID: {self.reg_id}" if has_reg_id else "⚠️ 未指定规程ID，必须首先调用 locate_regulations"

            user_prompt = f"""用户查询：{query}

上下文信息：{context_info}

规程ID状态：{reg_id_hint}

请分析查询意图，规划需要的 L1 子任务。"""

            # 调用 LLM 进行规划
            logger.debug(f"Calling LLM for planning with model: {self.llm_model}")
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
            # 检查 response 和 choices 是否存在
            logger.debug(f"LLM response type: {type(response)}, has choices: {hasattr(response, 'choices')}")
            if hasattr(response, 'choices') and response.choices:
                logger.debug(f"Number of choices: {len(response.choices)}")

            if not response or not response.choices or len(response.choices) == 0:
                logger.error(f"LLM returned invalid response: response={response}")
                raise ValueError("LLM returned empty response or no choices")

            content = response.choices[0].message.content
            if not content:
                raise ValueError("LLM returned empty content")

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

            # 提取并记录推理过程
            reasoning = planning_result.get("reasoning", "")
            subtasks_data = planning_result.get("subtasks", [])

            # 记录完整的规划推理到日志
            logger.info(f"LLM Planning Reasoning: {reasoning}")

            # 将推理过程保存到 hierarchy_manager 的共享上下文中
            if self.hierarchy_manager:
                self.hierarchy_manager.update_agent_status(
                    agent_id=self.agent_id,
                    status="thinking",
                    thinking=f"规划推理: {reasoning}"
                )

            # 发布规划阶段事件，包含推理过程
            phase_change_event("planning", reasoning)

            # 转换为内部格式
            subtasks = []
            for subtask_data in subtasks_data:
                subagent_type_str = subtask_data.get("type", "")
                try:
                    subagent_type = SubagentType(subagent_type_str)
                    params = subtask_data.get("params", {})

                    # 只有在 reg_id 存在且子任务不是 locate_regulations 时才注入 reg_id
                    # locate_regulations 不需要 reg_id，它的作用就是找到 reg_id
                    if self.reg_id and subagent_type != SubagentType.LOCATE_REGULATIONS:
                        params["reg_id"] = self.reg_id

                    subtask = {
                        "type": subagent_type,
                        "params": params,
                        "reason": subtask_data.get("reason", ""),
                        "expected_output": subtask_data.get("expected_output", ""),
                    }
                    subtasks.append(subtask)

                    # 记录每个子任务的详细信息
                    logger.info(
                        f"Planned subtask: {subagent_type.value} | "
                        f"Reason: {subtask['reason']} | "
                        f"Expected: {subtask['expected_output']}"
                    )
                except ValueError:
                    logger.warning(f"Invalid subagent type: {subagent_type_str}")
                    continue

            # 如果 LLM 没有返回任何有效子任务，使用默认策略
            if not subtasks:
                logger.warning("LLM planning returned no valid subtasks, using default")
                subtasks = self._fallback_planning(query)

            # 去重：确保 locate_regulations 只出现一次
            subtasks = self._deduplicate_locate_regulations(subtasks)

            logger.info(f"Planned {len(subtasks)} subtasks: {[st['type'].value for st in subtasks]}")
            return subtasks

        except Exception as e:
            logger.error(f"LLM planning failed: {e}, using fallback")
            return self._fallback_planning(query)

    def _deduplicate_locate_regulations(
        self, subtasks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """去重 locate_regulations 子任务

        确保 locate_regulations 只出现一次，且在最前面。

        Args:
            subtasks: 原始子任务列表

        Returns:
            去重后的子任务列表
        """
        locate_reg_tasks = []
        other_tasks = []

        for subtask in subtasks:
            if subtask["type"] == SubagentType.LOCATE_REGULATIONS:
                locate_reg_tasks.append(subtask)
            else:
                other_tasks.append(subtask)

        # 如果有多个 locate_regulations，只保留第一个
        if len(locate_reg_tasks) > 1:
            logger.warning(
                f"Found {len(locate_reg_tasks)} locate_regulations tasks, "
                f"keeping only the first one"
            )
            locate_reg_tasks = locate_reg_tasks[:1]

        # locate_regulations 必须在最前面
        return locate_reg_tasks + other_tasks

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

        # 如果没有 reg_id，首先添加 locate_regulations
        if not self.reg_id:
            subtasks.append({
                "type": SubagentType.LOCATE_REGULATIONS,
                "params": {"query": query},
                "reason": "未指定规程ID，需要先定位规程",
            })

        # 简单的关键词匹配规则
        if any(kw in query_lower for kw in ["章", "节", "目录", "哪些"]):
            params = {"query": query}
            if self.reg_id:
                params["reg_id"] = self.reg_id
            subtasks.append({
                "type": SubagentType.LOCATE_CHAPTERS,
                "params": params,
                "reason": "查询包含章节相关关键词",
            })

        if any(kw in query_lower for kw in ["表", "表格"]):
            params = {"query": query}
            if self.reg_id:
                params["reg_id"] = self.reg_id
            subtasks.append({
                "type": SubagentType.FIND_TABLES,
                "params": params,
                "reason": "查询包含表格相关关键词",
            })

        if any(kw in query_lower for kw in ["注", "见", "参照", "参见"]):
            params = {"query": query}
            if self.reg_id:
                params["reg_id"] = self.reg_id
            subtasks.append({
                "type": SubagentType.RESOLVE_REFERENCES,
                "params": params,
                "reason": "查询包含引用相关关键词",
            })

        # 如果没有匹配到特定任务，使用语义搜索作为默认
        if not subtasks or (len(subtasks) == 1 and subtasks[0]["type"] == SubagentType.LOCATE_REGULATIONS):
            params = {"query": query}
            if self.reg_id:
                params["reg_id"] = self.reg_id
            subtasks.append({
                "type": SubagentType.SEMANTIC_SEARCH,
                "params": params,
                "reason": "默认使用语义搜索",
            })

        return subtasks

    async def _execute_subtask(self, subtask: dict[str, Any]) -> dict[str, Any]:
        """执行单个子任务

        根据子任务类型调用相应的 MCP 工具执行。

        Args:
            subtask: 子任务定义（包含 type 和 params）

        Returns:
            子任务执行结果
        """
        subagent_type = subtask["type"]
        params = subtask["params"]

        # 生成子智能体 ID
        subagent_id = f"{subagent_type.value}_{uuid.uuid4().hex[:8]}"

        # 创建子任务追踪节点
        subtask_node_id = f"subtask_{subagent_id}"
        self.tracer.add_node(
            subtask_node_id,
            NodeType.SUBTASK,
            subagent_type.value,
            parent_id=f"query_{self.agent_id}"
        )
        self.tracer.start_node(subtask_node_id)

        # 注册子智能体到 HierarchyManager
        self.hierarchy_manager.push_agent(
            agent_id=subagent_id,
            agent_name=subagent_type.value,
            parent_id=self.agent_id,
            level=1,
            user_input=params.get("query", ""),
        )

        logger.info(f"Executing L1 subtask: {subagent_type.value}")

        # 发送子任务开始事件
        await self._send_event(tool_start_event(
            tool_name=subagent_type.value,
            tool_input=params
        ))

        subtask_start = time.time()

        # 根据子任务类型调用相应的执行方法
        try:
            if subagent_type == SubagentType.LOCATE_REGULATIONS:
                output = await self._execute_locate_regulations(params)
            elif subagent_type == SubagentType.LOCATE_CHAPTERS:
                output = await self._execute_locate_chapters(params)
            elif subagent_type == SubagentType.FETCH_CONTENT:
                output = await self._execute_fetch_content(params)
            elif subagent_type == SubagentType.FIND_TABLES:
                output = await self._execute_find_tables(params)
            elif subagent_type == SubagentType.RESOLVE_REFERENCES:
                output = await self._execute_resolve_references(params)
            elif subagent_type == SubagentType.SEMANTIC_SEARCH:
                output = await self._execute_semantic_search(params)
            else:
                raise ValueError(f"Unknown subagent type: {subagent_type}")

            result = {
                "subagent_type": subagent_type.value,
                "status": "completed",
                "output": output,
            }

        except Exception as e:
            logger.error(f"Subtask {subagent_type.value} failed: {e}")
            result = {
                "subagent_type": subagent_type.value,
                "status": "failed",
                "output": f"执行失败: {str(e)}",
                "error": str(e),
            }
            # 记录错误
            self.metrics.record_error(
                error_type=type(e).__name__,
                labels={"subtask_type": subagent_type.value}
            )
            # 标记节点失败
            self.tracer.complete_node(subtask_node_id, NodeStatus.FAILED)

        # 记录子任务执行时间
        subtask_elapsed = time.time() - subtask_start
        self.metrics.record_subtask_latency(
            subagent_type.value,
            subtask_elapsed,
            labels={"status": result["status"]}
        )

        # 完成子任务追踪（如果还未标记）
        if result["status"] == "completed":
            self.tracer.complete_node(subtask_node_id, NodeStatus.SUCCESS)

        # 发送子任务结束事件
        await self._send_event(tool_end_event(
            tool_name=subagent_type.value,
            duration_ms=subtask_elapsed * 1000,
            result_summary=result.get("output", "")[:200] if result.get("output") else "执行完成"
        ))

        # 更新子智能体状态
        self.hierarchy_manager.update_agent_status(
            agent_id=subagent_id,
            status=result["status"],
            output=result["output"],
        )

        # 从栈中移除子智能体
        self.hierarchy_manager.pop_agent(subagent_id)
        self.hierarchy_manager.save_state()

        return result

    async def _aggregate_results(
        self,
        subtask_results: list[dict[str, Any]],
        original_query: str
    ) -> str:
        """使用 LLM 聚合子任务结果

        将多个 L1 子任务的结果智能聚合成连贯的最终回答。

        Args:
            subtask_results: 子任务结果列表
            original_query: 用户的原始查询

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
            user_prompt = f"""用户的原始问题：{original_query}

以下是子任务的执行结果：

{results_text}

请基于这些结果，直接回答用户的原始问题。要求：
1. 直接回答问题，不要泛泛而谈
2. 如果结果中包含答案，提取并整合
3. 如果结果不足以回答问题，明确指出缺少什么信息
4. 保留关键的来源信息（页码、章节号等）"""

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

            # 检查 response 和 choices 是否存在
            if not response or not response.choices or len(response.choices) == 0:
                raise ValueError("LLM returned empty response or no choices")

            aggregated_result = response.choices[0].message.content
            if not aggregated_result:
                raise ValueError("LLM returned empty aggregation result")

            logger.info("Successfully aggregated results using LLM")
            return aggregated_result.strip()

        except Exception as e:
            logger.error(f"LLM aggregation failed: {e}, using fallback")
            return self._fallback_aggregation(subtask_results, original_query)

    def _fallback_aggregation(
        self,
        subtask_results: list[dict[str, Any]],
        original_query: str
    ) -> str:
        """回退聚合策略（简单拼接）

        当 LLM 聚合失败时使用。

        Args:
            subtask_results: 子任务结果列表
            original_query: 用户的原始查询

        Returns:
            聚合后的结果
        """
        aggregated_parts = [f"【用户问题】\n{original_query}\n"]
        for result in subtask_results:
            subagent_type = result.get("subagent_type", "unknown")
            output = result.get("output", "")
            aggregated_parts.append(f"【{subagent_type}】\n{output}")

        return "\n\n".join(aggregated_parts)

    async def _execute_subtasks_sequential(
        self, subtasks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """顺序执行子任务

        Args:
            subtasks: 子任务列表

        Returns:
            子任务结果列表
        """
        logger.info(f"Sequential execution mode: {len(subtasks)} subtasks")
        subtask_results = []
        for subtask in subtasks:
            # 在执行前动态注入 reg_id（如果当前有 reg_id 且子任务参数中没有）
            if self.reg_id and "reg_id" not in subtask["params"]:
                # 只有非 locate_regulations 子任务才需要 reg_id
                if subtask["type"] != SubagentType.LOCATE_REGULATIONS:
                    subtask["params"]["reg_id"] = self.reg_id
                    logger.debug(f"Injected reg_id={self.reg_id} into {subtask['type'].value}")

            result = await self._execute_subtask(subtask)
            subtask_results.append(result)
        return subtask_results

    async def _execute_subtasks_parallel(
        self, subtasks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """并行执行子任务（考虑依赖关系）

        根据子任务之间的依赖关系，分批并行执行。
        同一批次内的子任务可以并行执行，不同批次按顺序执行。

        Args:
            subtasks: 子任务列表

        Returns:
            子任务结果列表（保持原始顺序）
        """
        logger.info(f"Parallel execution mode: {len(subtasks)} subtasks")

        # 1. 分析依赖关系，将子任务分批
        batches = self._group_subtasks_by_dependencies(subtasks)
        logger.debug(f"Grouped into {len(batches)} batches")

        # 记录并行度指标
        self.metrics.record_parallel_batch(len(batches))

        # 2. 生成并显示执行计划
        batch_plan_lines = []
        for i, batch in enumerate(batches, 1):
            batch_tasks = [st['type'].value for st in batch]
            if len(batch) > 1:
                batch_plan_lines.append(f"批次 {i} (并行): {', '.join(batch_tasks)}")
            else:
                batch_plan_lines.append(f"批次 {i} (顺序): {batch_tasks[0]}")

        batch_plan_text = "\n".join(batch_plan_lines)

        # 发送执行计划事件
        await self._send_event(phase_change_event(
            "execution",
            f"🔄 执行计划:\n{batch_plan_text}\n\n"
            f"共 {len(batches)} 个批次，{len(subtasks)} 个子任务"
        ))

        # 3. 按批次执行（批次间顺序，批次内并行）
        all_results = {}
        for batch_idx, batch in enumerate(batches, 1):
            logger.info(f"Executing batch {batch_idx}/{len(batches)} with {len(batch)} subtasks")

            batch_start = time.time()

            # 在执行前动态注入 reg_id（如果当前有 reg_id 且子任务参数中没有）
            for subtask in batch:
                if self.reg_id and "reg_id" not in subtask["params"]:
                    # 只有非 locate_regulations 子任务才需要 reg_id
                    if subtask["type"] != SubagentType.LOCATE_REGULATIONS:
                        subtask["params"]["reg_id"] = self.reg_id
                        logger.debug(f"Injected reg_id={self.reg_id} into {subtask['type'].value}")

            # 并行执行当前批次的所有子任务
            batch_tasks = [self._execute_subtask(subtask) for subtask in batch]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            batch_elapsed = time.time() - batch_start

            self.obs_logger.info(
                "Batch execution completed",
                batch_index=batch_idx,
                batch_size=len(batch),
                batch_time=batch_elapsed,
            )

            # 收集结果（处理异常）
            for subtask, result in zip(batch, batch_results):
                subtask_id = id(subtask)
                if isinstance(result, Exception):
                    logger.error(f"Subtask {subtask['type'].value} failed: {result}")
                    all_results[subtask_id] = {
                        "subagent_type": subtask["type"].value,
                        "status": "failed",
                        "output": f"执行失败: {str(result)}",
                        "error": str(result),
                    }
                    # 记录错误
                    self.metrics.record_error(
                        error_type=type(result).__name__,
                        labels={"subtask_type": subtask["type"].value}
                    )
                else:
                    all_results[subtask_id] = result

        # 3. 按原始顺序返回结果
        ordered_results = [all_results[id(subtask)] for subtask in subtasks]
        return ordered_results

    def _group_subtasks_by_dependencies(
        self, subtasks: list[dict[str, Any]]
    ) -> list[list[dict[str, Any]]]:
        """根据依赖关系将子任务分批

        使用拓扑排序算法，将有依赖关系的子任务分到不同批次。

        Args:
            subtasks: 子任务列表

        Returns:
            分批后的子任务列表，每个批次内的子任务可以并行执行
        """
        # 构建依赖图
        subtask_types = {id(st): st["type"] for st in subtasks}
        dependencies = {}  # {subtask_id: [依赖的subtask_id列表]}

        for subtask in subtasks:
            subtask_id = id(subtask)
            subtask_type = subtask["type"]
            dependencies[subtask_id] = []

            # 使用动态依赖函数
            required_types = get_subtask_dependencies(subtask_type, self.reg_id is not None)

            for other_subtask in subtasks:
                if other_subtask["type"] in required_types:
                    dependencies[subtask_id].append(id(other_subtask))

        # 拓扑排序分批
        batches = []
        remaining = set(subtask_types.keys())

        while remaining:
            # 找出当前批次可以执行的子任务（没有未满足的依赖）
            current_batch_ids = []
            for subtask_id in remaining:
                deps = dependencies[subtask_id]
                if all(dep_id not in remaining for dep_id in deps):
                    current_batch_ids.append(subtask_id)

            if not current_batch_ids:
                # 检测到循环依赖，强制执行剩余任务
                logger.warning("Circular dependency detected, forcing execution")
                current_batch_ids = list(remaining)

            # 构建当前批次
            current_batch = [st for st in subtasks if id(st) in current_batch_ids]
            batches.append(current_batch)

            # 从剩余集合中移除
            remaining -= set(current_batch_ids)

        return batches

    # ==================== L1 子任务执行方法 ====================

    async def _execute_locate_regulations(self, params: dict[str, Any]) -> str:
        """执行 LOCATE_REGULATIONS 子任务

        使用 locate_regulations 工具自动定位相关规程。

        **重要**：此方法会解析返回结果，提取最佳匹配的 reg_id，
        并更新 self.reg_id，以便后续子任务使用。

        Args:
            params: 包含 query, top_k, min_score

        Returns:
            匹配的规程列表的文本描述
        """
        # 状态检查：如果已经有 reg_id，跳过执行
        if self.reg_id:
            logger.info(f"locate_regulations: 已有 reg_id={self.reg_id}，跳过执行")
            return f"已定位到规程: {self.reg_id}（跳过重复定位）"

        query = params.get("query", "")
        top_k = params.get("top_k", 3)
        min_score = params.get("min_score", 0.3)

        try:
            # 获取 MCP 客户端
            mcp_client = await self._get_mcp_client()

            # 调用 locate_regulations 工具
            result = await mcp_client.call_tool(
                "locate_regulations",
                arguments={
                    "query": query,
                    "top_k": top_k,
                    "min_score": min_score,
                }
            )

            # 尝试解析结果，提取 reg_id
            try:
                # 添加调试日志
                logger.debug(f"locate_regulations result type: {type(result)}")
                logger.debug(f"locate_regulations result: {result}")

                # result 可能是字符串或字典
                if isinstance(result, str):
                    import json
                    result_dict = json.loads(result)
                else:
                    result_dict = result

                # 提取匹配的规程列表
                matches = result_dict.get("matches", [])

                if matches:
                    # 使用得分最高的规程作为默认 reg_id
                    best_match = matches[0]
                    best_reg_id = best_match.get("reg_id")

                    # 使用锁保护 reg_id 更新操作（防止并行执行时的竞态条件）
                    async with self._reg_id_lock:
                        if best_reg_id and not self.reg_id:
                            # 更新 orchestrator 的 reg_id（仅当当前没有 reg_id 时）
                            self.reg_id = best_reg_id
                            logger.info(f"locate_regulations: 自动设置 reg_id = {best_reg_id}")

                            # 同时更新 hierarchy_manager 的状态
                            self.hierarchy_manager.update_agent_status(
                                agent_id=self.agent_id,
                                status="thinking",
                                thinking=f"已定位到规程: {best_reg_id}",
                            )
                            self.hierarchy_manager.save_state()

            except Exception as parse_error:
                logger.warning(f"Failed to parse locate_regulations result: {parse_error}")
                # 解析失败不影响返回结果

            # 格式化输出
            output = f"已执行规程定位查询：{query}\n\n"
            output += f"定位结果：\n{result}"

            return output

        except Exception as e:
            logger.error(f"locate_regulations failed: {e}")
            return f"规程定位失败: {str(e)}"

    async def _execute_locate_chapters(self, params: dict[str, Any]) -> str:
        """执行 LOCATE_CHAPTERS 子任务

        使用 get_toc 工具获取目录结构，分析并返回相关章节。

        Args:
            params: 包含 query 和 reg_id

        Returns:
            章节列表的文本描述
        """
        query = params.get("query", "")
        reg_id = params.get("reg_id", self.reg_id)

        if not reg_id:
            return "错误：未指定规程ID"

        try:
            # 获取 MCP 客户端
            mcp_client = await self._get_mcp_client()

            # 调用 get_toc 工具
            toc_result = await mcp_client.call_tool("get_toc", {"reg_id": reg_id})

            # 简单解析：提取章节信息
            # TODO: 可以使用 LLM 进行更智能的章节匹配
            output = f"已获取规程 {reg_id} 的目录结构。\n\n"
            output += f"相关查询：{query}\n\n"
            output += f"目录信息：\n{toc_result}"

            return output

        except Exception as e:
            logger.error(f"LOCATE_CHAPTERS failed: {e}")
            return f"定位章节失败: {str(e)}"

    async def _execute_fetch_content(self, params: dict[str, Any]) -> str:
        """执行 FETCH_CONTENT 子任务

        使用 read_chapter_content 或 read_page_range 获取章节内容。

        Args:
            params: 包含 query, reg_id, chapter_number 等

        Returns:
            章节内容文本
        """
        query = params.get("query", "")
        reg_id = params.get("reg_id", self.reg_id)
        chapter_number = params.get("chapter_number")

        if not reg_id:
            return "错误：未指定规程ID"

        try:
            mcp_client = await self._get_mcp_client()

            # 如果指定了章节号，使用 read_chapter_content
            if chapter_number:
                result = await mcp_client.call_tool(
                    "read_chapter_content",
                    {"reg_id": reg_id, "section_number": chapter_number}
                )
                output = f"章节 {chapter_number} 的内容：\n\n{result}"
            else:
                # 否则使用 smart_search 搜索相关内容
                result = await mcp_client.call_tool(
                    "smart_search",
                    {"query": query, "reg_id": reg_id, "limit": 5}
                )
                output = f"搜索结果：\n\n{result}"

            return output

        except Exception as e:
            logger.error(f"FETCH_CONTENT failed: {e}")
            return f"获取内容失败: {str(e)}"

    async def _execute_find_tables(self, params: dict[str, Any]) -> str:
        """执行 FIND_TABLES 子任务

        使用 search_tables 搜索表格，然后使用 get_table_by_id 获取完整内容。

        Args:
            params: 包含 query, reg_id 等

        Returns:
            表格搜索结果
        """
        query = params.get("query", "")
        reg_id = params.get("reg_id", self.reg_id)

        if not reg_id:
            return "错误：未指定规程ID"

        try:
            mcp_client = await self._get_mcp_client()

            # 搜索表格
            result = await mcp_client.call_tool(
                "search_tables",
                {"query": query, "reg_id": reg_id, "mode": "hybrid", "limit": 5}
            )

            output = f"表格搜索结果：\n\n{result}"
            return output

        except Exception as e:
            logger.error(f"FIND_TABLES failed: {e}")
            return f"查找表格失败: {str(e)}"

    async def _execute_resolve_references(self, params: dict[str, Any]) -> str:
        """执行 RESOLVE_REFERENCES 子任务

        使用 resolve_reference 或 lookup_annotation 解析引用。

        Args:
            params: 包含 query, reg_id, reference_text 等

        Returns:
            引用解析结果
        """
        query = params.get("query", "")
        reg_id = params.get("reg_id", self.reg_id)
        reference_text = params.get("reference_text", query)

        if not reg_id:
            return "错误：未指定规程ID"

        try:
            mcp_client = await self._get_mcp_client()

            # 尝试解析引用
            result = await mcp_client.call_tool(
                "resolve_reference",
                {"reg_id": reg_id, "reference_text": reference_text}
            )

            output = f"引用解析结果：\n\n{result}"
            return output

        except Exception as e:
            logger.error(f"RESOLVE_REFERENCES failed: {e}")
            return f"解析引用失败: {str(e)}"

    async def _execute_semantic_search(self, params: dict[str, Any]) -> str:
        """执行 SEMANTIC_SEARCH 子任务

        使用 smart_search 或 find_similar_content 进行语义搜索。

        Args:
            params: 包含 query, reg_id 等

        Returns:
            语义搜索结果
        """
        query = params.get("query", "")
        reg_id = params.get("reg_id", self.reg_id)

        if not reg_id:
            return "错误：未指定规程ID"

        try:
            mcp_client = await self._get_mcp_client()

            # 使用 smart_search 进行语义搜索
            result = await mcp_client.call_tool(
                "smart_search",
                {"query": query, "reg_id": reg_id, "limit": 10}
            )

            output = f"语义搜索结果：\n\n{result}"
            return output

        except Exception as e:
            logger.error(f"SEMANTIC_SEARCH failed: {e}")
            return f"语义搜索失败: {str(e)}"
