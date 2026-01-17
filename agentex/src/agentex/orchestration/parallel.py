"""并行执行器

支持多个子智能体/任务的并发执行。
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Awaitable


@dataclass
class ExecutionResult:
    """执行结果"""
    task_id: str
    success: bool
    result: Any = None
    error: str | None = None
    duration_ms: float = 0.0


class ParallelExecutor:
    """并行执行器

    特点：
    - 支持顺序/并行两种模式
    - 自动收集来源和工具调用
    - 支持部分失败容忍
    """

    def __init__(
        self,
        mode: str = "parallel",
        fail_strategy: str = "continue"  # "continue" | "stop" | "all_or_nothing"
    ):
        """初始化执行器

        Args:
            mode: 执行模式，"sequential" 或 "parallel"
            fail_strategy: 失败策略
        """
        self.mode = mode
        self.fail_strategy = fail_strategy

    async def execute(
        self,
        tasks: list[tuple[str, Callable[[], Awaitable[Any]]]],
    ) -> list[ExecutionResult]:
        """执行任务列表

        Args:
            tasks: [(task_id, task_func), ...]

        Returns:
            list[ExecutionResult]: 执行结果列表
        """
        results: list[ExecutionResult] = []

        if self.mode == "sequential":
            for task_id, task_func in tasks:
                try:
                    start = asyncio.get_event_loop().time()
                    result = await task_func()
                    duration_ms = (asyncio.get_event_loop().time() - start) * 1000
                    results.append(ExecutionResult(
                        task_id=task_id,
                        success=True,
                        result=result,
                        duration_ms=duration_ms,
                    ))
                except Exception as e:
                    results.append(ExecutionResult(
                        task_id=task_id,
                        success=False,
                        error=str(e),
                    ))
                    if self.fail_strategy == "stop":
                        break

        else:  # parallel
            async def run_task(task_id: str, task_func: Callable[[], Awaitable[Any]]) -> ExecutionResult:
                start = asyncio.get_event_loop().time()
                try:
                    result = await task_func()
                    duration_ms = (asyncio.get_event_loop().time() - start) * 1000
                    return ExecutionResult(
                        task_id=task_id,
                        success=True,
                        result=result,
                        duration_ms=duration_ms,
                    )
                except Exception as e:
                    return ExecutionResult(
                        task_id=task_id,
                        success=False,
                        error=str(e),
                    )

            # 并发执行
            coroutines = [run_task(tid, fn) for tid, fn in tasks]
            raw_results = await asyncio.gather(*coroutines, return_exceptions=True)

            for r in raw_results:
                if isinstance(r, Exception):
                    results.append(ExecutionResult(
                        task_id="unknown",
                        success=False,
                        error=str(r),
                    ))
                else:
                    results.append(r)

        return results

    async def execute_with_aggregation(
        self,
        tasks: list[tuple[str, Callable[[], Awaitable[Any]]]],
        aggregator: Callable[[list[ExecutionResult]], Any],
    ) -> tuple[Any, list[ExecutionResult]]:
        """执行任务并聚合结果

        Args:
            tasks: 任务列表
            aggregator: 聚合函数，接收所有执行结果

        Returns:
            (聚合结果, 执行结果列表)
        """
        results = await self.execute(tasks)
        aggregated = aggregator(results)
        return aggregated, results


class TaskPool:
    """任务池

    管理并发任务的数量限制。
    """

    def __init__(self, max_concurrent: int = 10):
        """初始化任务池

        Args:
            max_concurrent: 最大并发数
        """
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.running: set[asyncio.Task] = set()

    async def submit(self, coro: Awaitable[Any]) -> Any:
        """提交任务

        Args:
            coro: 协程

        Returns:
            任务结果
        """
        async with self.semaphore:
            task = asyncio.create_task(coro)
            self.running.add(task)
            task.add_done_callback(self.running.discard)
            return await task

    async def map(
        self,
        func: Callable[[Any], Awaitable[Any]],
        items: list[Any],
    ) -> list[Any]:
        """并发映射

        Args:
            func: 异步函数
            items: 数据列表

        Returns:
            结果列表
        """
        return await asyncio.gather(*[
            self.submit(func(item)) for item in items
        ])

    @property
    def active_count(self) -> int:
        """当前活跃任务数"""
        return len(self.running)
