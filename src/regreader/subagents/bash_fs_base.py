"""Bash+FS 范式的子智能体基类

支持文件系统通信的子智能体基类，用于新的两层架构。
子智能体从 task.md 读取任务，执行原子操作，记录到 steps.md 和 results.json。
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import json
from loguru import logger


@dataclass
class SubagentResult:
    """子智能体执行结果

    Attributes:
        content: 最终答案（处理后）
        sources: 数据来源列表
        tool_calls: 工具调用序列
        metadata: 元数据（包含完整执行记录）
    """

    content: str
    """最终答案"""

    sources: list[str]
    """数据来源（如 reg_id:page_num 格式）"""

    tool_calls: list[str]
    """工具调用序列（原子操作）"""

    metadata: dict[str, Any]
    """元数据（包含完整执行记录）"""

    def summary(self) -> str:
        """生成结果摘要

        Returns:
            摘要文本（用于返回给主智能体）
        """
        return f"""执行完成。

**工具调用序列**: {" → ".join(self.tool_calls)}

**数据来源**:
{chr(10).join(f"- {source}" for source in self.sources)}

**答案**:
{self.content}
"""


class BaseSubagentFS(ABC):
    """子智能体基类（Bash+FS 范式）

    支持：
    - Claude Agent SDK 封装
    - Pydantic AI 封装
    - LangGraph 封装

    工作流程：
    1. 从 task.md 读取主智能体分发的任务
    2. 主动拆解为原子操作序列
    3. 执行原子操作（调用 MCP 工具）
    4. 记录过程到 steps.md（实时更新，支持断点续传）
    5. 写入结果到 results.json
    """

    def __init__(
        self,
        workspace: Path,
        reg_id: str,
        framework: str = "claude",  # claude | pydantic | langgraph
        mcp_transport: str | None = None,  # 从 CLI 传递
        mcp_host: str | None = None,  # 从 CLI 传递
        mcp_port: int | None = None,  # 从 CLI 传递
    ):
        """初始化子智能体

        Args:
            workspace: 工作区路径
            reg_id: 规程 ID
            framework: 框架类型（claude/pydantic/langgraph）
            mcp_transport: MCP 传输方式（stdio/sse）
            mcp_host: MCP 主机地址
            mcp_port: MCP 端口
        """
        self.workspace = workspace
        self.reg_id = reg_id
        self.framework = framework

        # MCP 配置（优先使用传递的参数，否则从配置读取）
        from regreader.core.config import get_settings
        settings = get_settings()

        self.mcp_transport = mcp_transport or settings.mcp_transport
        self.mcp_host = mcp_host or settings.mcp_host
        self.mcp_port = mcp_port or settings.mcp_port

        # 创建工作目录
        self.workspace.mkdir(parents=True, exist_ok=True)
        (self.workspace / "logs").mkdir(exist_ok=True)

        logger.info(
            f"SubagentFS 初始化: framework={framework}, reg_id={reg_id}, workspace={workspace}"
        )

    def read_task(self) -> str:
        """从 task.md 读取主智能体分发的任务

        Returns:
            任务内容（Markdown 格式）

        Raises:
            FileNotFoundError: 任务文件不存在
        """
        task_file = self.workspace / "task.md"
        if not task_file.exists():
            raise FileNotFoundError(f"任务文件不存在: {task_file}")

        content = task_file.read_text(encoding="utf-8")
        logger.debug(f"读取任务文件: {task_file}")

        return content

    def write_steps(self, steps: list[dict[str, Any]]):
        """写入原子任务拆解到 steps.md

        Args:
            steps: 原子任务列表，每个包含 step, description, action, timestamp, params, result
        """
        steps_file = self.workspace / "steps.md"

        content = "# 原子任务执行记录\n\n"

        for step in steps:
            content += f"""## 步骤 {step['step']}: {step['description']}

**操作**: {step['action']}
**时间**: {step['timestamp']}
**参数**: {json.dumps(step.get('params', {}), ensure_ascii=False, indent=2)}
**结果**: {json.dumps(step.get('result', {}), ensure_ascii=False, indent=2)}

---
"""

        steps_file.write_text(content, encoding="utf-8")
        logger.debug(f"更新步骤文件: {steps_file} (共 {len(steps)} 步)")

    def write_results(self, results: dict[str, Any]):
        """写入最终结果到 results.json

        Args:
            results: 结果字典
        """
        results_file = self.workspace / "results.json"
        results_file.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(f"写入结果文件: {results_file}")

    @abstractmethod
    def decompose_task(self, task: str) -> list[dict[str, Any]]:
        """将任务拆解为原子操作

        这是子智能体核心能力：主动识别任务，决定如何拆解为原子操作。

        Args:
            task: 任务描述（从 task.md 读取）

        Returns:
            原子操作列表，每个操作包含：
            - step: 步骤编号（1, 2, 3...）
            - description: 步骤描述
            - action: 操作类型（工具名称）
            - params: 工具参数（在 execute_atomic_step 中使用）

        Examples:
            >>> task = "从规程目录中定位关于母线失压的章节"
            >>> decompose_task(task)
            [
                {
                    "step": 1,
                    "description": "获取规程目录结构",
                    "action": "get_toc",
                    "params": {"reg_id": "angui_2024"}
                },
                {
                    "step": 2,
                    "description": "在目录中搜索母线失压相关章节",
                    "action": "smart_search",
                    "params": {
                        "query": "母线失压",
                        "reg_id": "angui_2024",
                        "chapter_scope": "第六章"
                    }
                }
            ]
        """
        pass

    @abstractmethod
    async def execute_atomic_step(self, step: dict[str, Any]) -> Any:
        """执行单个原子操作（异步）

        Args:
            step: 原子操作定义（来自 decompose_task）

        Returns:
            操作结果

        Examples:
            >>> step = {
            ...     "step": 1,
            ...     "description": "获取规程目录结构",
            ...     "action": "get_toc",
            ...     "params": {"reg_id": "angui_2024"}
            ... }
            >>> await execute_atomic_step(step)
            {"toc": [...], "reg_id": "angui_2024"}
        """
        pass

    def _aggregate_results(self, steps: list[dict[str, Any]]) -> str:
        """聚合所有步骤的结果，生成最终答案

        Args:
            steps: 执行完成的步骤列表

        Returns:
            最终答案（处理后）
        """
        # 默认实现：提取所有结果，用换行连接
        results = []
        for step in steps:
            result = step.get("result", {})
            if isinstance(result, dict):
                # 提取关键信息
                if "content" in result:
                    results.append(result["content"])
                elif "answer" in result:
                    results.append(result["answer"])
                else:
                    results.append(str(result))
            else:
                results.append(str(result))

        return "\n\n".join(results)

    def _extract_sources(self, steps: list[dict[str, Any]]) -> list[str]:
        """从步骤中提取数据来源

        Args:
            steps: 执行完成的步骤列表

        Returns:
            数据来源列表（如 ["angui_2024:10", "angui_2024:15"]）
        """
        sources = []
        for step in steps:
            result = step.get("result", {})
            if isinstance(result, dict):
                # 提取 source 字段
                if "source" in result:
                    sources.append(result["source"])
                elif "sources" in result:
                    sources.extend(result["sources"])
                elif "page_num" in result:
                    sources.append(f"{self.reg_id}:{result['page_num']}")

        return sources

    def run(self) -> SubagentResult:
        """执行任务（主流程）

        Returns:
            SubagentResult: 执行结果
        """
        logger.info(f"开始执行任务: {self.workspace / 'task.md'}")

        # 1. 读取任务
        task_content = self.read_task()

        # 2. 拆解为原子操作
        logger.info("拆解任务为原子操作...")
        steps = self.decompose_task(task_content)
        logger.info(f"拆解完成，共 {len(steps)} 个原子操作")

        # 3. 执行原子操作（使用 asyncio.run 运行异步步骤）
        logger.info("开始执行原子操作...")

        async def _execute_steps():
            """内部异步函数，执行所有步骤"""
            executed_steps = []
            for step in steps:
                step["timestamp"] = datetime.now().isoformat()

                logger.info(f"执行步骤 {step['step']}: {step['description']}")

                try:
                    step["result"] = await self.execute_atomic_step(step)
                    step["status"] = "completed"
                    logger.info(f"步骤 {step['step']} 完成")
                except Exception as e:
                    step["result"] = {"error": str(e)}
                    step["status"] = "failed"
                    logger.error(f"步骤 {step['step']} 失败: {e}")
                    # 继续执行其他步骤

                executed_steps.append(step)

                # 实时写入步骤（支持断点续传）
                self.write_steps(executed_steps)

            return executed_steps

        # 运行异步步骤执行
        try:
            # 检查是否已有运行中的事件循环
            try:
                loop = asyncio.get_running_loop()
                # 已有事件循环，使用 create_task
                import concurrent.futures
                import threading

                if threading.current_thread() is threading.main_thread():
                    # 在主线程中，可以使用 run_coroutine_threadsafe
                    future = asyncio.run_coroutine_threadsafe(
                        _execute_steps(), loop
                    )
                    executed_steps = future.result(timeout=300)  # 5分钟超时
                else:
                    # 在其他线程中，创建新的事件循环
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(
                            asyncio.run, _execute_steps()
                        )
                        executed_steps = future.result()
            except RuntimeError:
                # 没有事件循环，创建新的
                executed_steps = asyncio.run(_execute_steps())
        except Exception as e:
            logger.error(f"异步执行失败: {e}")
            raise

        # 4. 聚合结果
        logger.info("聚合执行结果...")
        results = {
            "task": task_content,
            "steps": executed_steps,
            "final_answer": self._aggregate_results(executed_steps),
            "completed_at": datetime.now().isoformat(),
            "status": "completed" if all(
                s.get("status") != "failed" for s in executed_steps
            ) else "partial",
        }

        # 5. 写入结果
        self.write_results(results)

        # 6. 构造返回对象
        result = SubagentResult(
            content=results["final_answer"],
            sources=self._extract_sources(executed_steps),
            tool_calls=[step["action"] for step in executed_steps],
            metadata=results,
        )

        logger.info(f"任务执行完成: status={results['status']}")
        return result
