"""主智能体：任务级拆解和调度

⚠️ DEPRECATED: 此实现已废弃，请使用新的 OrchestratorAgent 架构。

使用 Claude Agent SDK + preset: "claude_code" 实现主智能体。
主智能体负责将用户查询拆解为任务级子任务，然后通过文件系统分发给子智能体。

迁移指南:
- 旧方式: regreader ask "..." --main-agent -r angui_2024
- 新方式: regreader ask "..." --mode orchestrated -r angui_2024
- 或使用: regreader ask "..." -o -r angui_2024

新架构优势:
- 基于 infiAgent 的层级化智能体架构
- HierarchyManager 进行父子追踪和状态持久化
- 工具白名单强制执行
- 支持三个框架 (Claude SDK / Pydantic AI / LangGraph)
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

# Claude Agent SDK imports
try:
    from claude_agent_sdk import (
        ClaudeAgentOptions,
        ClaudeSDKClient,
    )
    HAS_CLAUDE_SDK = True
except ImportError:
    HAS_CLAUDE_SDK = False
    ClaudeAgentOptions = None  # type: ignore
    ClaudeSDKClient = None  # type: ignore

from loguru import logger

from regreader.core.config import get_settings


class MainAgent:
    """主智能体：任务级拆解和调度

    ⚠️ DEPRECATED: 此类已废弃，请使用 OrchestratorAgent。

    使用 Claude Agent SDK + preset: "claude_code"

    职责：
    1. 任务级拆解：将用户查询拆解为任务（不是原子工具调用）
    2. 子任务调度：通过文件系统向子智能体分发任务
    3. 执行记录：记录任务拆解、子任务分发、结果聚合过程
    4. 结果聚合：整合所有子智能体的结果，生成最终答案
    """

    def __init__(
        self,
        reg_id: str,
        session_id: str | None = None,
        workspace_root: Path = Path("./coordinator"),
        model: str | None = None,
        api_key: str | None = None,
        mcp_transport: str | None = None,
        mcp_host: str | None = None,
        mcp_port: int | None = None,
        status_callback: Any | None = None,
    ):
        """初始化主智能体

        Args:
            reg_id: 规程 ID
            session_id: 会话 ID（可选，默认自动生成）
            workspace_root: 工作区根目录
            model: 模型名称（可选，默认从配置读取）
            api_key: API 密钥（可选，默认从配置读取）
            mcp_transport: MCP 传输方式（可选，从 CLI 传递）
            mcp_host: MCP 主机地址（可选，从 CLI 传递）
            mcp_port: MCP 端口（可选，从 CLI 传递）
            status_callback: 状态回调（可选，用于显示工作步骤）
        """
        if not HAS_CLAUDE_SDK:
            raise ImportError(
                "claude-agent-sdk 未安装。请运行: pip install claude-agent-sdk"
            )

        # 废弃警告
        import warnings
        warnings.warn(
            "MainAgent 已废弃，请使用 OrchestratorAgent。"
            "使用 --mode orchestrated 或 -o 标志启用新架构。",
            DeprecationWarning,
            stacklevel=2
        )
        logger.warning(
            "⚠️  MainAgent 已废弃，请迁移到 OrchestratorAgent。"
            "新架构提供更好的层级化智能体管理和工具访问控制。"
        )

        self.reg_id = reg_id
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.workspace_root = workspace_root
        self.session_dir = workspace_root / f"session_{self.session_id}"
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # 状态回调（用于显示工作步骤）
        self.status_callback = status_callback
        self._step_counter = 0  # 步骤计数器

        # 获取配置
        settings = get_settings()
        self.model = model or settings.llm_model_name
        self.api_key = api_key or settings.llm_api_key

        # MCP 配置（优先使用传递的参数，否则从配置读取）
        self.mcp_transport = mcp_transport or settings.mcp_transport
        self.mcp_host = mcp_host or settings.mcp_host
        self.mcp_port = mcp_port or settings.mcp_port

        # 配置 Claude Agent SDK 以支持 Skills
        self.agent_options = ClaudeAgentOptions(
            cwd=Path.cwd(),  # 当前工作目录（包含 .claude/skills/）
            setting_sources=["user", "project"],  # 加载用户和项目级 Skills
            allowed_tools=["Skill"],  # 启用 Skills 机制
            model=self.model,
        )

        # 初始化 Claude SDK Client（稍后在 query 时创建）
        self.client: ClaudeSDKClient | None = None

    def _emit_step_start(self, description: str) -> int:
        """发出步骤开始事件

        Args:
            description: 步骤描述

        Returns:
            步骤编号
        """
        self._step_counter += 1
        step_num = self._step_counter

        if self.status_callback and hasattr(self.status_callback, 'on_step_start'):
            self.status_callback.on_step_start(step_num, description)

        return step_num

    def _emit_step_end(self, step_num: int, result_summary: str = ""):
        """发出步骤结束事件

        Args:
            step_num: 步骤编号
            result_summary: 结果摘要
        """
        if self.status_callback and hasattr(self.status_callback, 'on_step_end'):
            self.status_callback.on_step_end(step_num, result_summary)

    def _build_main_prompt(self) -> str:
        """构建主智能体提示词"""
        return """你是 RegReader 主智能体，负责处理用户查询。

# 你的职责（任务级，非原子工具调用）

你需要将用户查询拆解为**任务级子任务**，例如：
- "从规程目录中定位可能的章节"
- "从指定章节范围获得与问题任务相关的内容或表格"
- "查找并提取相关的表格数据"
- "解析交叉引用"

# 你不应该做的事情
❌ 不要直接调用底层 MCP 工具（get_toc, smart_search 等）
❌ 不要拆解为"调用 get_toc()"、"调用 read_page_range()"这样的原子操作

# 子智能体职责
子智能体会收到你的任务，然后**自己决定如何拆解为原子操作**并执行。
子智能体会记录其原子任务拆解和执行过程到各自的工作区。

# 可用的任务分发工具
- dispatch_search_task: 分发搜索任务（定位章节、提取内容）
- dispatch_table_task: 分发表格任务（查找表格、提取数据）
- dispatch_reference_task: 分发引用任务（解析交叉引用）

# 工作流程
1. 理解用户查询
2. 拆解为任务级子任务（1-3个）
3. 调用相应的分发工具
4. 等待子智能体完成
5. 聚合结果，生成最终答案
"""

    async def _dispatch_search_task(self, task_description: str) -> str:
        """分发搜索任务到 SearchAgent

        Args:
            task_description: 任务描述（任务级，非原子操作）
                例如："从规程目录中定位关于母线失压的章节"

        Returns:
            子智能体返回的结果摘要
        """
        # 1. 写入任务文件到子智能体工作区
        task_file = self.workspace_root.parent / "subagents" / "search" / "task.md"
        task_file.parent.mkdir(parents=True, exist_ok=True)

        task_content = f"""# 搜索任务

## 任务描述
{task_description}

## 接收时间
{datetime.now().isoformat()}

## 上下文
- 规程 ID: {self.reg_id}
- 会话 ID: {self.session_id}

## 执行要求
请将此任务拆解为原子操作并执行：
1. 分析任务，识别需要哪些步骤
2. 调用相应的 MCP 工具（get_toc, smart_search, read_page_range 等）
3. 记录你的执行过程到 steps.md
4. 返回结果到 results.json
"""
        task_file.write_text(task_content, encoding="utf-8")

        # 2. 记录到主智能体执行日志
        self._log_execution(
            action="dispatch_task",
            target="search",
            details={"task_description": task_description}
        )

        # 3. 调用 SearchAgent（在线程中运行同步代码）
        from regreader.subagents.search.agent import SearchAgent

        search_agent = SearchAgent(
            workspace=self.workspace_root.parent / "subagents" / "search",
            reg_id=self.reg_id,
            mcp_transport=self.mcp_transport,
            mcp_host=self.mcp_host,
            mcp_port=self.mcp_port,
        )
        result = await asyncio.to_thread(search_agent.run)

        # 4. 返回结果摘要
        summary = result.summary()
        return summary

    async def _dispatch_table_task(self, task_description: str) -> str:
        """分发表格任务到 TableAgent

        Args:
            task_description: 任务描述（任务级）
                例如："查找并提取相关的表格数据"

        Returns:
            子智能体返回的结果摘要
        """
        # 1. 写入任务文件到子智能体工作区
        task_file = self.workspace_root.parent / "subagents" / "table" / "task.md"
        task_file.parent.mkdir(parents=True, exist_ok=True)

        task_content = f"""# 表格任务

## 任务描述
{task_description}

## 接收时间
{datetime.now().isoformat()}

## 上下文
- 规程 ID: {self.reg_id}
- 会话 ID: {self.session_id}

## 执行要求
请将此任务拆解为原子操作并执行：
1. 分析任务，识别需要哪些步骤
2. 调用相应的 MCP 工具（search_tables, get_table_by_id 等）
3. 记录你的执行过程到 steps.md
4. 返回结果到 results.json
"""
        task_file.write_text(task_content, encoding="utf-8")

        # 2. 记录到主智能体执行日志
        self._log_execution(
            action="dispatch_task",
            target="table",
            details={"task_description": task_description}
        )

        # 3. 调用 TableAgent（在线程中运行同步代码）
        from regreader.subagents.table.agent import TableAgent

        table_agent = TableAgent(
            workspace=self.workspace_root.parent / "subagents" / "table",
            reg_id=self.reg_id,
            mcp_transport=self.mcp_transport,
            mcp_host=self.mcp_host,
            mcp_port=self.mcp_port,
        )
        result = await asyncio.to_thread(table_agent.run)

        # 4. 返回结果摘要
        return result.summary()

    async def _dispatch_reference_task(self, task_description: str) -> str:
        """分发引用任务到 ReferenceAgent

        Args:
            task_description: 任务描述（任务级）
                例如："解析交叉引用"

        Returns:
            子智能体返回的结果摘要
        """
        # 1. 写入任务文件到子智能体工作区
        task_file = (
            self.workspace_root.parent / "subagents" / "reference" / "task.md"
        )
        task_file.parent.mkdir(parents=True, exist_ok=True)

        task_content = f"""# 引用任务

## 任务描述
{task_description}

## 接收时间
{datetime.now().isoformat()}

## 上下文
- 规程 ID: {self.reg_id}
- 会话 ID: {self.session_id}

## 执行要求
请将此任务拆解为原子操作并执行：
1. 分析任务，识别需要哪些步骤
2. 调用相应的 MCP 工具（resolve_reference, lookup_annotation 等）
3. 记录你的执行过程到 steps.md
4. 返回结果到 results.json
"""
        task_file.write_text(task_content, encoding="utf-8")

        # 2. 记录到主智能体执行日志
        self._log_execution(
            action="dispatch_task",
            target="reference",
            details={"task_description": task_description}
        )

        # 3. 调用 ReferenceAgent（在线程中运行同步代码）
        from regreader.subagents.reference.agent import ReferenceAgent

        reference_agent = ReferenceAgent(
            workspace=self.workspace_root.parent / "subagents" / "reference",
            reg_id=self.reg_id,
            mcp_transport=self.mcp_transport,
            mcp_host=self.mcp_host,
            mcp_port=self.mcp_port,
        )
        result = await asyncio.to_thread(reference_agent.run)

        # 4. 返回结果摘要
        return result.summary()

    def _log_execution(self, action: str, target: str, details: dict[str, Any]):
        """记录执行过程到 execution.md

        Args:
            action: 动作名称
            target: 目标子智能体
            details: 详细信息
        """
        execution_log = self.session_dir / "execution.md"

        log_entry = f"""
## {action} - {datetime.now().isoformat()}

**目标**: {target}
**详情**: {json.dumps(details, ensure_ascii=False, indent=2)}

---
"""

        with open(execution_log, "a", encoding="utf-8") as f:
            f.write(log_entry)

        logger.debug(f"记录执行日志: {action} -> {target}")

    async def _decompose_task_with_llm(self, user_query: str) -> list[dict[str, Any]]:
        """使用 LLM 拆解用户查询为任务级子任务

        Args:
            user_query: 用户查询

        Returns:
            任务级子任务列表
        """
        # 构建任务拆解提示词
        system_prompt = "你是任务拆解专家，只返回 JSON 格式的任务列表。"

        user_prompt = f"""请将以下用户查询拆解为任务级子任务。

# 用户查询
{user_query}

# 规程 ID
{self.reg_id}

# 可用的任务类型
1. search: 搜索任务（定位章节、提取内容）
2. table: 表格任务（查找表格、提取数据）
3. reference: 引用任务（解析交叉引用）

# 任务级描述示例
- "从规程目录中定位关于母线失压的章节"
- "从指定章节范围获得与问题任务相关的内容或表格"
- "查找并提取相关的表格数据"
- "解析交叉引用"

# 输出格式
请返回 JSON 格式的任务列表：
[
    {{
        "task_type": "search",
        "description": "从规程目录中定位关于母线失压的章节"
    }},
    {{
        "task_type": "table",
        "description": "查找并提取相关的表格数据"
    }}
]

只返回 JSON，不要其他内容。
"""

        try:
            # 使用 AsyncOpenAI 而不是同步的 OpenAI
            import os
            from openai import AsyncOpenAI

            settings = get_settings()

            # 处理 Ollama 后端 URL（需要添加 /v1 后缀）
            base_url = settings.llm_base_url
            if settings.is_ollama_backend() and not base_url.endswith("/v1"):
                base_url = base_url.rstrip("/") + "/v1"

            # API key 回退逻辑：优先使用配置，然后尝试环境变量
            api_key = settings.llm_api_key or os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("OPENAI_API_KEY") or "dummy"

            client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
            )

            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
            )

            result_text = response.choices[0].message.content
            if not result_text:
                raise ValueError("LLM 返回空响应")

            # 解析 JSON
            # 提取 JSON（可能被包裹在 ```json 中）
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()

            tasks = json.loads(result_text)
            return tasks

        except Exception as e:
            logger.error(f"LLM 拆解失败: {e}")
            return self._rule_based_decomposition(user_query)

    def _rule_based_decomposition(self, user_query: str) -> list[dict[str, Any]]:
        """基于规则拆解用户查询（回退方案）

        Args:
            user_query: 用户查询

        Returns:
            任务级子任务列表
        """
        logger.info("使用规则拆解任务")

        tasks = []

        # 规则 1: 如果涉及"目录"、"章节"，添加 search 任务
        if any(keyword in user_query for keyword in ["目录", "章节", "定位"]):
            tasks.append({
                "task_type": "search",
                "description": f"从规程目录中定位与查询相关的章节: {user_query}"
            })

        # 规则 2: 如果涉及"表格"、"数据"，添加 table 任务
        if any(keyword in user_query for keyword in ["表格", "表", "数据"]):
            tasks.append({
                "task_type": "table",
                "description": f"查找并提取相关的表格数据: {user_query}"
            })

        # 规则 3: 如果涉及"引用"、"参见"，添加 reference 任务
        if any(keyword in user_query for keyword in ["引用", "参见", "见"]):
            tasks.append({
                "task_type": "reference",
                "description": f"解析交叉引用: {user_query}"
            })

        # 如果没有匹配任何规则，默认使用 search
        if not tasks:
            tasks.append({
                "task_type": "search",
                "description": f"搜索相关内容: {user_query}"
            })

        logger.info(f"规则拆解完成，共 {len(tasks)} 个子任务")
        return tasks

    async def query(self, user_query: str) -> str:
        """处理用户查询

        Args:
            user_query: 用户查询

        Returns:
            最终答案
        """
        # 发出查询开始事件
        query_step = self._emit_step_start(f"处理查询: {user_query[:50]}...")

        # 1. 写入初始任务计划
        plan_step = self._emit_step_start("创建执行计划")
        plan_file = self.session_dir / "plan.md"
        plan_content = f"""# 执行计划

## 用户查询
{user_query}

## 创建时间
{datetime.now().isoformat()}

## 规程
{self.reg_id}

## 任务拆解
（待主智能体生成）
"""
        plan_file.write_text(plan_content, encoding="utf-8")
        self._emit_step_end(plan_step, f"计划文件: {plan_file}")

        # 2. 循环迭代执行（最多 3 次）
        all_results = []
        max_iterations = 3
        missing_info = ""

        for iteration in range(max_iterations):
            # 2.1 拆解任务（首次或精炼）
            if iteration == 0:
                decompose_step = self._emit_step_start("分析查询并拆解任务")
                tasks = await self._decompose_task_with_llm(user_query)
                self._emit_step_end(decompose_step, f"拆解为 {len(tasks)} 个子任务")
            else:
                tasks = await self._generate_refinement_tasks(
                    user_query, missing_info, all_results
                )
                if not tasks:
                    break

            # 更新计划文件
            plan_content += f"\n\n## 迭代 {iteration + 1} 子任务列表\n\n"
            for i, task in enumerate(tasks, 1):
                plan_content += f"{i}. **{task['task_type']}**: {task['description']}\n"
            plan_file.write_text(plan_content, encoding="utf-8")

            # 2.2 执行子任务
            iteration_results = []
            for idx, task in enumerate(tasks, 1):
                task_type = task["task_type"]
                description = task["description"]

                # 发出子任务开始事件
                subtask_step = self._emit_step_start(f"子任务 {idx}/{len(tasks)}: {task_type} - {description[:30]}...")

                # 根据任务类型分发到相应的子智能体
                if task_type == "search":
                    result_summary = await self._dispatch_search_task(description)
                    self._emit_step_end(subtask_step, f"搜索完成")
                elif task_type == "table":
                    result_summary = await self._dispatch_table_task(description)
                    self._emit_step_end(subtask_step, f"表格查询完成")
                elif task_type == "reference":
                    result_summary = await self._dispatch_reference_task(description)
                    self._emit_step_end(subtask_step, f"引用解析完成")
                else:
                    continue

                iteration_results.append({
                    "task_type": task_type,
                    "description": description,
                    "result": result_summary
                })

            # 2.3 累积结果
            all_results.extend(iteration_results)

            # 2.4 检查完成度
            is_completed, missing_info = await self._check_completion(
                user_query, all_results
            )

            if is_completed:
                break

        # 3. 使用 LLM 聚合结果
        aggregation_step = self._emit_step_start("聚合所有子任务结果")
        aggregation_prompt = f"""你是结果聚合专家。请整合以下子任务结果，生成最终答案。

# 用户查询
{user_query}

# 子任务结果
"""

        for i, result in enumerate(all_results, 1):
            aggregation_prompt += f"""
## 子任务 {i}: {result['task_type']}
**描述**: {result['description']}
**结果**: {result['result']}
"""

        aggregation_prompt += """
请基于以上子任务结果，生成一个清晰、完整的最终答案。
"""

        try:
            import os
            from openai import AsyncOpenAI

            settings = get_settings()
            base_url = settings.llm_base_url
            if settings.is_ollama_backend() and not base_url.endswith("/v1"):
                base_url = base_url.rstrip("/") + "/v1"

            # API key 回退逻辑：优先使用配置，然后尝试环境变量
            api_key = settings.llm_api_key or os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("OPENAI_API_KEY") or "dummy"

            client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
            )

            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是结果聚合专家，负责整合多个子任务的执行结果。"},
                    {"role": "user", "content": aggregation_prompt},
                ],
                temperature=0.3,
            )

            final_answer = response.choices[0].message.content
            if not final_answer:
                raise ValueError("LLM 返回空响应")

            self._emit_step_end(aggregation_step, f"生成最终答案 ({len(final_answer)} 字符)")

        except Exception as e:
            logger.error(f"结果聚合失败: {e}")
            # 回退：直接拼接所有结果
            final_answer = "\n\n".join([
                f"### 子任务 {i}: {r['task_type']}\n{r['result']}"
                for i, r in enumerate(all_results, 1)
            ])

        # 5. 写入最终报告
        report_file = self.session_dir / "final_report.md"
        report_content = f"""# 最终报告

## 查询
{user_query}

## 答案
{final_answer}

## 生成时间
{datetime.now().isoformat()}

## 子任务执行记录
"""

        for i, result in enumerate(all_results, 1):
            report_content += f"""
### 子任务 {i}: {result['task_type']}
- **描述**: {result['description']}
- **结果**: {result['result'][:200]}...
"""

        report_file.write_text(report_content, encoding="utf-8")

        # 发出查询完成事件
        self._emit_step_end(query_step, f"查询完成，生成答案 ({len(final_answer)} 字符)")

        return final_answer

    def get_session_info(self) -> dict[str, Any]:
        """获取会话信息

        Returns:
            会话信息字典
        """
        return {
            "session_id": self.session_id,
            "reg_id": self.reg_id,
            "session_dir": str(self.session_dir),
            "workspace_root": str(self.workspace_root),
        }

    async def _check_completion(
        self,
        user_query: str,
        completed_tasks: list[dict[str, Any]]
    ) -> tuple[bool, str]:
        """检查任务完成度

        使用 LLM 判断当前结果是否充分回答了用户查询。

        Args:
            user_query: 用户查询
            completed_tasks: 已完成的任务列表

        Returns:
            (是否完成, 缺失信息描述)
        """
        # 聚合所有任务结果
        aggregated_result = "\n\n".join([
            f"### 任务 {i}: {t.get('task_type', 'unknown')}\n{t.get('result', '')}"
            for i, t in enumerate(completed_tasks, 1)
        ])

        # 构建检查提示词
        check_prompt = f"""你是任务完成度评估专家。请判断以下结果是否充分回答了用户查询。

用户查询：{user_query}

当前结果：
{aggregated_result}

请回答：
1. 是否完成（是/否）
2. 如果未完成，缺少哪些信息？

返回 JSON 格式：
{{
  "completed": true/false,
  "missing_info": "缺失信息描述（如果已完成则为空）"
}}
"""

        try:
            import os
            from openai import AsyncOpenAI

            settings = get_settings()
            base_url = settings.llm_base_url
            if settings.is_ollama_backend() and not base_url.endswith("/v1"):
                base_url = base_url.rstrip("/") + "/v1"

            # API key 回退逻辑：优先使用配置，然后尝试环境变量
            api_key = settings.llm_api_key or os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("OPENAI_API_KEY") or "dummy"

            client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
            )

            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是任务完成度评估专家，只返回 JSON 格式。"},
                    {"role": "user", "content": check_prompt},
                ],
                temperature=0.3,
            )

            result_text = response.choices[0].message.content
            if not result_text:
                raise ValueError("LLM 返回空响应")

            # 解析 JSON
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()

            data = json.loads(result_text)
            return data.get("completed", False), data.get("missing_info", "")

        except Exception as e:
            logger.error(f"完成度检查失败: {e}")
            # 默认认为已完成
            return True, ""

    async def _generate_refinement_tasks(
        self,
        user_query: str,
        missing_info: str,
        completed_tasks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """生成精炼任务

        基于缺失信息，生成新的子任务以补充。

        Args:
            user_query: 用户查询
            missing_info: 缺失信息描述
            completed_tasks: 已完成的任务列表

        Returns:
            精炼任务列表
        """
        # 构建精炼提示词
        refinement_prompt = f"""你是任务精炼专家。基于当前结果和缺失信息，生成新的子任务。

用户查询：{user_query}

缺失信息：{missing_info}

已完成任务：
{json.dumps([t.get('description', '') for t in completed_tasks], ensure_ascii=False)}

请生成新的子任务来补充缺失信息。返回 JSON 格式：
[
  {{
    "task_type": "search",
    "description": "任务描述"
  }}
]
"""

        try:
            import os
            from openai import AsyncOpenAI

            settings = get_settings()
            base_url = settings.llm_base_url
            if settings.is_ollama_backend() and not base_url.endswith("/v1"):
                base_url = base_url.rstrip("/") + "/v1"

            # API key 回退逻辑：优先使用配置，然后尝试环境变量
            api_key = settings.llm_api_key or os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("OPENAI_API_KEY") or "dummy"

            client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
            )

            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是任务精炼专家，只返回 JSON 格式的任务列表。"},
                    {"role": "user", "content": refinement_prompt},
                ],
                temperature=0.3,
            )

            result_text = response.choices[0].message.content
            if not result_text:
                raise ValueError("LLM 返回空响应")

            # 解析 JSON
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()

            tasks = json.loads(result_text)
            return tasks

        except Exception as e:
            logger.error(f"精炼任务生成失败: {e}")
            return []
