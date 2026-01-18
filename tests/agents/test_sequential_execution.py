"""Sequential vs Parallel Execution Comparison Tests

对比顺序执行和并发执行的行为和结果。

测试目标：
1. 验证顺序执行和并发执行产生相同结果
2. 验证顺序执行和并发执行的性能差异
3. 验证错误处理的一致性
4. 验证结果聚合的一致性
"""

import asyncio
import time
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from regreader.subagents.config import SubagentType

from .test_concurrent_execution import (
    MockCallback,
    MockSubgraphBuilder,
    create_mock_orchestrator_state,
)


# ============================================================================
# Sequential vs Parallel Comparison Tests
# ============================================================================


class TestSequentialParallelConsistency:
    """测试顺序执行和并发执行的一致性"""

    @pytest.mark.asyncio
    async def test_same_results_sequential_vs_parallel(self):
        """验证顺序和并发执行产生相同结果"""
        # 创建子图构建器
        builders = {
            SubagentType.SEARCH: MockSubgraphBuilder(
                SubagentType.SEARCH,
                delay=0.02,
                content="搜索结果"
            ),
            SubagentType.TABLE: MockSubgraphBuilder(
                SubagentType.TABLE,
                delay=0.02,
                content="表格结果"
            ),
        }

        selected = ["search", "table"]
        query = "测试查询"
        reg_id = "test_reg"
        hints = {"chapter_scope": "第六章"}

        # 顺序执行
        sequential_results = []
        for type_value in selected:
            agent_type = SubagentType(type_value)
            result = await builders[agent_type].invoke(query, reg_id, hints)
            sequential_results.append(result)

        # 重置计数器
        for builder in builders.values():
            builder.invoke_count = 0
            builder.invoke_history.clear()

        # 并发执行
        parallel_results = await asyncio.gather(*[
            builders[SubagentType(type_value)].invoke(query, reg_id, hints)
            for type_value in selected
        ])

        # 验证结果数量
        assert len(sequential_results) == len(parallel_results)

        # 验证每个结果的内容
        for seq_result, par_result in zip(sequential_results, parallel_results):
            assert seq_result["content"] == par_result["content"]
            assert seq_result["sources"] == par_result["sources"]
            assert len(seq_result["tool_calls"]) == len(par_result["tool_calls"])

    @pytest.mark.asyncio
    async def test_execution_order_consistency(self):
        """验证执行顺序的一致性"""
        # 创建带时间戳的 Mock 子图
        execution_log_sequential = []
        execution_log_parallel = []

        class LoggingMockBuilder(MockSubgraphBuilder):
            """记录执行顺序的 Mock Builder"""

            def __init__(self, agent_type: SubagentType, log: list):
                super().__init__(agent_type, delay=0.01)
                self.log = log

            async def invoke(self, query: str, reg_id: str | None, hints: dict) -> dict:
                self.log.append({
                    "agent": self.agent_type.value,
                    "timestamp": time.time(),
                    "mode": "invoke"
                })
                result = await super().invoke(query, reg_id, hints)
                self.log.append({
                    "agent": self.agent_type.value,
                    "timestamp": time.time(),
                    "mode": "complete"
                })
                return result

        # 顺序执行
        builders_seq = {
            SubagentType.SEARCH: LoggingMockBuilder(SubagentType.SEARCH, execution_log_sequential),
            SubagentType.TABLE: LoggingMockBuilder(SubagentType.TABLE, execution_log_sequential),
            SubagentType.REFERENCE: LoggingMockBuilder(SubagentType.REFERENCE, execution_log_sequential),
        }

        selected = ["search", "table", "reference"]

        for type_value in selected:
            agent_type = SubagentType(type_value)
            await builders_seq[agent_type].invoke("查询", "test", {})

        # 并发执行
        execution_log_parallel.clear()
        builders_par = {
            SubagentType.SEARCH: LoggingMockBuilder(SubagentType.SEARCH, execution_log_parallel),
            SubagentType.TABLE: LoggingMockBuilder(SubagentType.TABLE, execution_log_parallel),
            SubagentType.REFERENCE: LoggingMockBuilder(SubagentType.REFERENCE, execution_log_parallel),
        }

        await asyncio.gather(*[
            builders_par[SubagentType(type_value)].invoke("查询", "test", {})
            for type_value in selected
        ])

        # 验证：顺序执行应严格有序
        assert execution_log_sequential[0]["agent"] == "search"
        assert execution_log_sequential[1]["mode"] == "complete"
        assert execution_log_sequential[2]["agent"] == "table"
        assert execution_log_sequential[3]["mode"] == "complete"

        # 验证：并发执行应同时启动（所有 invoke 在任何 complete 之前）
        invoke_indices = [
            i for i, log in enumerate(execution_log_parallel)
            if log["mode"] == "invoke"
        ]
        complete_indices = [
            i for i, log in enumerate(execution_log_parallel)
            if log["mode"] == "complete"
        ]

        # 所有 invoke 应在所有 complete 之前
        assert max(invoke_indices) < min(complete_indices)


class TestSequentialParallelPerformance:
    """测试顺序执行和并发执行的性能对比"""

    @pytest.mark.asyncio
    async def test_speedup_measurement(self):
        """测量并发执行的加速比"""
        # 创建多个子图
        num_subagents = 4
        delay = 0.05

        builders = [
            MockSubgraphBuilder(
                SubagentType.SEARCH,
                delay=delay,
                content=f"结果{i}"
            )
            for i in range(num_subagents)
        ]

        # 顺序执行
        start_time = time.time()
        for builder in builders:
            await builder.invoke("查询", "test", {})
        sequential_time = time.time() - start_time

        # 重置
        for builder in builders:
            builder.invoke_count = 0

        # 并发执行
        start_time = time.time()
        await asyncio.gather(*[
            builder.invoke("查询", "test", {}) for builder in builders
        ])
        parallel_time = time.time() - start_time

        # 计算加速比
        speedup = sequential_time / parallel_time

        # 验证
        print(f"\n顺序执行时间: {sequential_time:.3f}s")
        print(f"并发执行时间: {parallel_time:.3f}s")
        print(f"加速比: {speedup:.2f}x")

        # 并发执行应显著快于顺序执行
        assert speedup >= 2.0, f"加速比 {speedup:.2f}x 低于期望的 2.0x"

        # 顺序执行时间应约为 num_subagents * delay
        assert sequential_time >= num_subagents * delay * 0.9

        # 并发执行时间应约为 delay（加上少量开销）
        assert parallel_time < delay * 2.0

    @pytest.mark.asyncio
    async def test_speedup_with_varying_delays(self):
        """测试不同延迟下的加速比"""
        test_cases = [
            (2, 0.02),  # 2个子图，每个20ms
            (3, 0.03),  # 3个子图，每个30ms
            (4, 0.04),  # 4个子图，每个40ms
        ]

        for num_subagents, delay in test_cases:
            builders = [
                MockSubgraphBuilder(SubagentType.SEARCH, delay=delay)
                for _ in range(num_subagents)
            ]

            # 顺序执行
            start_time = time.time()
            for builder in builders:
                await builder.invoke("查询", "test", {})
            sequential_time = time.time() - start_time

            # 重置
            for builder in builders:
                builder.invoke_count = 0

            # 并发执行
            start_time = time.time()
            await asyncio.gather(*[
                builder.invoke("查询", "test", {}) for builder in builders
            ])
            parallel_time = time.time() - start_time

            speedup = sequential_time / parallel_time

            # 验证加速比合理
            assert speedup >= 1.5, f"{num_subagents}个子图，加速比{speedup:.2f}x过低"

            print(f"{num_subagents}个子图，延迟{delay}s: 加速比 {speedup:.2f}x")

    @pytest.mark.asyncio
    async def test_efficiency_with_many_subagents(self):
        """测试多子智能体时的并发效率"""
        num_subagents = 8
        delay = 0.02

        builders = [
            MockSubgraphBuilder(SubagentType.SEARCH, delay=delay)
            for _ in range(num_subagents)
        ]

        # 顺序执行
        start_time = time.time()
        for builder in builders:
            await builder.invoke("查询", "test", {})
        sequential_time = time.time() - start_time

        # 重置
        for builder in builders:
            builder.invoke_count = 0

        # 并发执行
        start_time = time.time()
        await asyncio.gather(*[
            builder.invoke("查询", "test", {}) for builder in builders
        ])
        parallel_time = time.time() - start_time

        # 计算效率
        theoretical_speedup = num_subagents
        actual_speedup = sequential_time / parallel_time
        efficiency = actual_speedup / theoretical_speedup

        print(f"\n{num_subagents}个子图:")
        print(f"理论加速比: {theoretical_speedup}x")
        print(f"实际加速比: {actual_speedup:.2f}x")
        print(f"并发效率: {efficiency*100:.1f}%")

        # 验证效率合理（应>50%）
        assert efficiency > 0.5, f"并发效率{efficiency*100:.1f}%过低"


class TestSequentialParallelErrorHandling:
    """测试顺序和并发执行的错误处理一致性"""

    @pytest.mark.asyncio
    async def test_error_handling_consistency(self):
        """验证错误处理的一致性"""
        # 创建部分失败的子图
        builders = {
            SubagentType.SEARCH: MockSubgraphBuilder(SubagentType.SEARCH, delay=0.02),
            SubagentType.TABLE: MockSubgraphBuilder(
                SubagentType.TABLE,
                delay=0.02,
                should_fail=True
            ),
            SubagentType.REFERENCE: MockSubgraphBuilder(SubagentType.REFERENCE, delay=0.02),
        }

        selected = ["search", "table", "reference"]

        # 顺序执行（捕获异常）
        sequential_success = 0
        sequential_failure = 0
        for type_value in selected:
            try:
                await builders[SubagentType(type_value)].invoke("查询", "test", {})
                sequential_success += 1
            except Exception:
                sequential_failure += 1

        # 重置
        for builder in builders.values():
            builder.invoke_count = 0

        # 并发执行（使用 return_exceptions=True）
        results = await asyncio.gather(*[
            builders[SubagentType(type_value)].invoke("查询", "test", {})
            for type_value in selected
        ], return_exceptions=True)

        parallel_success = sum(1 for r in results if not isinstance(r, Exception))
        parallel_failure = sum(1 for r in results if isinstance(r, Exception))

        # 验证一致性
        assert sequential_success == parallel_success
        assert sequential_failure == parallel_failure
        assert sequential_success == 2
        assert sequential_failure == 1

    @pytest.mark.asyncio
    async def test_error_isolation_sequential_vs_parallel(self):
        """验证错误隔离的一致性"""
        # 创建子图：第一个失败，不应影响后续
        builders = [
            MockSubgraphBuilder(SubagentType.SEARCH, delay=0.02, should_fail=True),
            MockSubgraphBuilder(SubagentType.TABLE, delay=0.02),
        ]

        # 顺序执行
        sequential_results = []
        for builder in builders:
            try:
                result = await builder.invoke("查询", "test", {})
                sequential_results.append(("success", result))
            except Exception as e:
                sequential_results.append(("error", str(e)))

        # 重置
        for builder in builders:
            builder.invoke_count = 0

        # 并发执行
        parallel_results_raw = await asyncio.gather(*[
            builder.invoke("查询", "test", {}) for builder in builders
        ], return_exceptions=True)

        parallel_results = []
        for result in parallel_results_raw:
            if isinstance(result, Exception):
                parallel_results.append(("error", str(result)))
            else:
                parallel_results.append(("success", result))

        # 验证
        assert len(sequential_results) == len(parallel_results)
        for seq, par in zip(sequential_results, parallel_results):
            assert seq[0] == par[0]  # 成功/失败状态一致


# ============================================================================
# Performance Benchmarks
# ============================================================================


class TestPerformanceBenchmarks:
    """性能基准测试"""

    @pytest.mark.asyncio
    async def test_benchmark_concurrent_execution(self):
        """基准测试：并发执行性能"""
        configurations = [
            (2, 0.05, "2个子图，50ms延迟"),
            (3, 0.05, "3个子图，50ms延迟"),
            (4, 0.05, "4个子图，50ms延迟"),
            (5, 0.05, "5个子图，50ms延迟"),
        ]

        results = []

        for num_subagents, delay, description in configurations:
            builders = [
                MockSubgraphBuilder(SubagentType.SEARCH, delay=delay)
                for _ in range(num_subagents)
            ]

            # 顺序执行
            start_time = time.time()
            for builder in builders:
                await builder.invoke("查询", "test", {})
            sequential_time = time.time() - start_time

            # 重置
            for builder in builders:
                builder.invoke_count = 0

            # 并发执行
            start_time = time.time()
            await asyncio.gather(*[
                builder.invoke("查询", "test", {}) for builder in builders
            ])
            parallel_time = time.time() - start_time

            speedup = sequential_time / parallel_time

            results.append({
                "config": description,
                "num_subagents": num_subagents,
                "delay": delay,
                "sequential_time": sequential_time,
                "parallel_time": parallel_time,
                "speedup": speedup,
            })

        # 打印结果
        print("\n并发执行性能基准测试结果:")
        print("=" * 80)
        for r in results:
            print(f"{r['config']}:")
            print(f"  顺序执行: {r['sequential_time']:.3f}s")
            print(f"  并发执行: {r['parallel_time']:.3f}s")
            print(f"  加速比: {r['speedup']:.2f}x")
            print()

        # 验证所有配置都有合理的加速比
        for r in results:
            assert r['speedup'] >= 1.5, f"{r['config']} 加速比过低"
