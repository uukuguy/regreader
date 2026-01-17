"""
并行执行示例

展示如何使用 AgentEx 的并行执行器同时执行多个任务。
"""

import asyncio
import time
from agentex.orchestration import ParallelExecutor, ExecutionResult


async def mock_task_1() -> str:
    """模拟任务1"""
    await asyncio.sleep(0.1)
    return "任务1结果"


async def mock_task_2() -> str:
    """模拟任务2"""
    await asyncio.sleep(0.2)
    return "任务2结果"


async def mock_task_3() -> str:
    """模拟任务3"""
    await asyncio.sleep(0.15)
    return "任务3结果"


async def mock_task_with_error() -> str:
    """模拟失败任务"""
    await asyncio.sleep(0.05)
    raise ValueError("模拟的错误")


async def main():
    """主函数"""
    print("=" * 60)
    print("并行执行示例")
    print("=" * 60)

    # === 示例1: 顺序执行 ===
    print("\n--- 顺序执行模式 ---")

    start_time = time.time()
    sequential_executor = ParallelExecutor(mode="sequential")

    sequential_results = await sequential_executor.execute([
        ("task_1", mock_task_1),
        ("task_2", mock_task_2),
        ("task_3", mock_task_3),
    ])

    sequential_time = time.time() - start_time
    print(f"顺序执行耗时: {sequential_time:.3f}秒")

    for result in sequential_results:
        if result.success:
            print(f"  ✓ {result.task_id}: {result.result}")
        else:
            print(f"  ✗ {result.task_id}: 错误 - {result.error}")

    # === 示例2: 并行执行 ===
    print("\n--- 并行执行模式 ---")

    start_time = time.time()
    parallel_executor = ParallelExecutor(mode="parallel")

    parallel_results = await parallel_executor.execute([
        ("task_1", mock_task_1),
        ("task_2", mock_task_2),
        ("task_3", mock_task_3),
    ])

    parallel_time = time.time() - start_time
    print(f"并行执行耗时: {parallel_time:.3f}秒")

    for result in parallel_results:
        if result.success:
            print(f"  ✓ {result.task_id}: {result.result}")
        else:
            print(f"  ✗ {result.task_id}: 错误 - {result.error}")

    # === 示例3: 错误处理 - 继续执行 ===
    print("\n--- 错误处理：继续执行模式 ---")

    error_continue_executor = ParallelExecutor(mode="parallel", fail_strategy="continue")

    error_continue_results = await error_continue_executor.execute([
        ("task_1", mock_task_1),
        ("task_error", mock_task_with_error),
        ("task_3", mock_task_3),
    ])

    for result in error_continue_results:
        if result.success:
            print(f"  ✓ {result.task_id}: {result.result}")
        else:
            print(f"  ✗ {result.task_id}: {result.error}")

    # === 示例4: 错误处理 - 立即失败 ===
    print("\n--- 错误处理：立即失败模式 ---")

    try:
        error_fail_executor = ParallelExecutor(mode="parallel", fail_strategy="fail_fast")

        error_fail_results = await error_fail_executor.execute([
            ("task_1", mock_task_1),
            ("task_error", mock_task_with_error),
            ("task_3", mock_task_3),
        ])

        for result in error_fail_results:
            if result.success:
                print(f"  ✓ {result.task_id}: {result.result}")
            else:
                print(f"  ✗ {result.task_id}: {result.error}")
    except Exception as e:
        print(f"  捕获到错误: {e}")

    # === 示例5: 性能对比 ===
    print("\n--- 性能对比 ---")
    print(f"顺序执行: {sequential_time:.3f}秒")
    print(f"并行执行: {parallel_time:.3f}秒")
    print(f"加速比: {sequential_time / parallel_time:.2f}x")


if __name__ == "__main__":
    asyncio.run(main())
