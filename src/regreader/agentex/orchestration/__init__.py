"""编排模块

提供多智能体编排和并行执行能力。
"""

from .parallel import ParallelExecutor, TaskPool, ExecutionResult

__all__ = [
    "ParallelExecutor",
    "TaskPool",
    "ExecutionResult",
]
