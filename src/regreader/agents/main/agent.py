"""主智能体：任务级拆解和调度

使用 Claude Agent SDK + preset: "claude_code" 实现主智能体。
主智能体负责将用户查询拆解为任务级子任务，然后通过文件系统分发给子智能体。
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
        """
        if not HAS_CLAUDE_SDK:
            raise ImportError(
                "claude-agent-sdk 未安装。请运行: pip install claude-agent-sdk"
            )

        self.reg_id = reg_id
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.workspace_root = workspace_root
        self.session_dir = workspace_root / f"session_{self.session_id}"
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # 获取配置
        settings = get_settings()
        self.model = model or settings.llm_model_name
        self.api_key = api_key or settings.llm_api_key

        # MCP 配置（优先使用传递的参数，否则从配置读取）
        self.mcp_transport = mcp_transport or settings.mcp_transport
        self.mcp_host = mcp_host or settings.mcp_host
        self.mcp_port = mcp_port or settings.mcp_port

        # 初始化 Claude SDK Client（稍后在 query 时创建）
        self.client: ClaudeSDKClient | None = None

        logger.info(
            f"MainAgent 初始化: reg_id={reg_id}, session_id={self.session_id}, mcp_transport={self.mcp_transport}"
        )

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

    def _dispatch_search_task(self, task_description: str) -> str:
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

        # 3. 调用 SearchAgent（在线程池中运行，避免事件循环冲突）
        from regreader.subagents.search.agent import SearchAgent
        import concurrent.futures

        def run_search_agent():
            search_agent = SearchAgent(
                workspace=self.workspace_root.parent / "subagents" / "search",
                reg_id=self.reg_id,
                mcp_transport=self.mcp_transport,
                mcp_host=self.mcp_host,
                mcp_port=self.mcp_port,
            )
            return search_agent.run()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_search_agent)
            result = future.result(timeout=300)  # 5分钟超时

        # 4. 返回结果摘要
        return result.summary()

    def _dispatch_table_task(self, task_description: str) -> str:
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

        # 3. 调用 TableAgent（在线程池中运行，避免事件循环冲突）
        from regreader.subagents.table.agent import TableAgent
        import concurrent.futures

        def run_table_agent():
            table_agent = TableAgent(
                workspace=self.workspace_root.parent / "subagents" / "table",
                reg_id=self.reg_id,
                mcp_transport=self.mcp_transport,
                mcp_host=self.mcp_host,
                mcp_port=self.mcp_port,
            )
            return table_agent.run()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_table_agent)
            result = future.result(timeout=300)  # 5分钟超时

        # 4. 返回结果摘要
        return result.summary()

    def _dispatch_reference_task(self, task_description: str) -> str:
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

        # 3. 调用 ReferenceAgent（在线程池中运行，避免事件循环冲突）
        from regreader.subagents.reference.agent import ReferenceAgent
        import concurrent.futures

        def run_reference_agent():
            reference_agent = ReferenceAgent(
                workspace=self.workspace_root.parent / "subagents" / "reference",
                reg_id=self.reg_id,
                mcp_transport=self.mcp_transport,
                mcp_host=self.mcp_host,
                mcp_port=self.mcp_port,
            )
            return reference_agent.run()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_reference_agent)
            result = future.result(timeout=300)  # 5分钟超时

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

    def _decompose_task_with_llm(self, user_query: str) -> list[dict[str, Any]]:
        """使用 LLM 拆解用户查询为任务级子任务

        Args:
            user_query: 用户查询

        Returns:
            任务级子任务列表
        """
        logger.info(f"使用 LLM 拆解任务: {user_query[:100]}...")

        # 构建任务拆解提示词
        decomposition_prompt = f"""你是任务拆解专家。请将以下用户查询拆解为任务级子任务。

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
            # 创建 Claude SDK Client（用于任务拆解）
            options = ClaudeAgentOptions(
                system_prompt="你是任务拆解专家，只返回 JSON 格式的任务列表。",
                model=self.model,  # model 通过 options 传递
            )

            async def get_decomposition():
                result = ""
                async with ClaudeSDKClient(options=options) as client:
                    # 发送查询
                    await client.query(decomposition_prompt, session_id="decomposition")

                    # 接收响应
                    async for event in client.receive_response():
                        if hasattr(event, "content"):
                            for block in event.content:
                                if hasattr(block, "text"):
                                    result += block.text
                return result

            # 检查是否已有运行中的事件循环
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 已有运行中的事件循环，使用 create_task
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(asyncio.run, get_decomposition())
                        response = future.result()
                else:
                    response = asyncio.run(get_decomposition())
            except RuntimeError:
                # 没有事件循环，创建新的
                response = asyncio.run(get_decomposition())

            # 解析 JSON
            # 提取 JSON（可能被包裹在 ```json 中）
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()

            tasks = json.loads(response)
            logger.info(f"LLM 拆解完成，共 {len(tasks)} 个子任务")
            return tasks

        except Exception as e:
            logger.warning(f"LLM 拆解失败，回退到规则拆解: {e}")
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
        # 1. 写入初始任务计划
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

        logger.info(f"开始处理查询: {user_query}")

        # 2. 使用 LLM 拆解任务
        tasks = self._decompose_task_with_llm(user_query)

        # 更新计划文件
        plan_content += "\n\n## 子任务列表\n\n"
        for i, task in enumerate(tasks, 1):
            plan_content += f"{i}. **{task['task_type']}**: {task['description']}\n"
        plan_file.write_text(plan_content, encoding="utf-8")

        # 3. 执行子任务
        all_results = []
        for task in tasks:
            task_type = task["task_type"]
            description = task["description"]

            logger.info(f"执行子任务: {task_type} - {description[:50]}...")

            # 根据任务类型分发到相应的子智能体
            if task_type == "search":
                result_summary = self._dispatch_search_task(description)
            elif task_type == "table":
                result_summary = self._dispatch_table_task(description)
            elif task_type == "reference":
                result_summary = self._dispatch_reference_task(description)
            else:
                logger.warning(f"未知任务类型: {task_type}")
                continue

            all_results.append({
                "task_type": task_type,
                "description": description,
                "result": result_summary
            })

        # 4. 使用 LLM 聚合结果
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
            async def get_aggregated_answer():
                result = ""
                async with ClaudeSDKClient(
                    options=ClaudeAgentOptions(
                        system_prompt="你是结果聚合专家，负责整合多个子任务的执行结果。",
                        model=self.model,  # model 通过 options 传递
                    )
                ) as client:
                    # 发送查询
                    await client.query(aggregation_prompt, session_id="aggregation")

                    # 接收响应
                    async for event in client.receive_response():
                        if hasattr(event, "content"):
                            for block in event.content:
                                if hasattr(block, "text"):
                                    result += block.text
                return result

            # 检查是否已有运行中的事件循环
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 已有运行中的事件循环，使用线程池
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(asyncio.run, get_aggregated_answer())
                        final_answer = future.result()
                else:
                    final_answer = asyncio.run(get_aggregated_answer())
            except RuntimeError:
                # 没有事件循环，创建新的
                final_answer = asyncio.run(get_aggregated_answer())

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

        logger.info(f"查询完成，结果已保存到: {report_file}")

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
