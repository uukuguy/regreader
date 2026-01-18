"""Concurrent Subagent Execution Tests

测试多子智能体并发执行的正确性和性能。

测试场景：
1. 并发执行基础功能测试
2. 并发与顺序执行结果一致性
3. 并发执行错误处理
4. 并发执行性能对比
5. 上下文传递测试
6. 结果聚合正确性
"""

import asyncio
import time
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from regreader.orchestration.result import SubagentResult
from regreader.subagents.config import SubagentType


# ============================================================================
# Test Utilities
# ============================================================================


class MockSubgraphBuilder:
    """Mock 子图构建器"""

    def __init__(
        self,
        agent_type: SubagentType,
        delay: float = 0.1,
        should_fail: bool = False,
        content: str = "Mock result",
    ):
        """初始化 Mock 子图

        Args:
            agent_type: 子智能体类型
            delay: 模拟执行延迟（秒）
            should_fail: 是否模拟失败
            content: 返回内容
        """
        self.agent_type = agent_type
        self.delay = delay
        self.should_fail = should_fail
        self.content = content
        self.invoke_count = 0
        self.invoke_history: list[dict] = []

    async def invoke(self, query: str, reg_id: str | None, hints: dict[str, Any]) -> dict:
        """模拟子图执行

        Args:
            query: 查询文本
            reg_id: 规程ID
            hints: 提示信息

        Returns:
            子图执行结果
        """
        self.invoke_count += 1

        # 记录调用历史
        self.invoke_history.append({
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "reg_id": reg_id,
            "hints": hints,
        })

        # 模拟延迟
        await asyncio.sleep(self.delay)

        # 模拟失败
        if self.should_fail:
            raise RuntimeError(f"Subagent {self.agent_type.value} failed")

        # 返回成功结果
        return {
            "content": f"[{self.agent_type.value}] {self.content}",
            "sources": [f"{reg_id or 'test'}:p1"],
            "tool_calls": [{"name": f"{self.agent_type.value}_tool", "input": query}],
            "success": True,
        }


def create_mock_orchestrator_state(
    query: str = "测试查询",
    reg_id: str = "test_reg",
    selected_subgraphs: list[str] | None = None,
    hints: dict[str, Any] | None = None,
) -> dict:
    """创建 Mock Orchestrator 状态

    Args:
        query: 查询文本
        reg_id: 规程ID
        selected_subgraphs: 选中的子图列表
        hints: 提示信息

    Returns:
        Orchestrator 状态字典
    """
    if selected_subgraphs is None:
        selected_subgraphs = ["search", "table"]

    return {
        "query": query,
        "reg_id": reg_id,
        "selected_subgraphs": selected_subgraphs,
        "hints": hints or {},
        "subgraph_results": {},
        "all_sources": [],
        "all_tool_calls": [],
        "final_content": "",
    }


class MockCallback:
    """Mock 回调对象"""

    def __init__(self):
        self.events: list[dict] = []

    async def on_event(self, event: dict) -> None:
        """记录事件"""
        self.events.append(event)


# ============================================================================
# Concurrent Execution Tests
# ============================================================================


class TestConcurrentExecutionBasics:
    """测试并发执行基础功能"""

    @pytest.mark.asyncio
    async def test_parallel_execution_with_multiple_subagents(self):
        """测试多个子智能体并发执行"""
        # 创建 Mock 子图构建器
        search_builder = MockSubgraphBuilder(
            SubagentType.SEARCH,
            delay=0.1,
            content="搜索结果"
        )
        table_builder = MockSubgraphBuilder(
            SubagentType.TABLE,
            delay=0.1,
            content="表格结果"
        )
        reference_builder = MockSubgraphBuilder(
            SubagentType.REFERENCE,
            delay=0.1,
            content="引用结果"
        )

        # 模拟并发执行
        selected = ["search", "table", "reference"]
        tasks = [
            search_builder.invoke("查询", "test", {}),
            table_builder.invoke("查询", "test", {}),
            reference_builder.invoke("查询", "test", {}),
        ]

        start_time = time.time()
        outputs = await asyncio.gather(*tasks, return_exceptions=True)
        duration = time.time() - start_time

        # 验证
        assert len(outputs) == 3
        assert all(isinstance(o, dict) for o in outputs)
        # 并发执行总时间应接近单个延迟时间（而非3倍）
        assert duration < 0.25  # 3 * 0.1 = 0.3，并发应小于0.25

        # 验证每个子图都被调用
        assert search_builder.invoke_count == 1
        assert table_builder.invoke_count == 1
        assert reference_builder.invoke_count == 1

    @pytest.mark.asyncio
    async def test_sequential_vs_parallel_execution_time(self):
        """对比顺序执行和并发执行的时间"""
        # 创建 Mock 子图构建器（固定延迟）
        delay = 0.05
        builders = {
            SubagentType.SEARCH: MockSubgraphBuilder(SubagentType.SEARCH, delay=delay),
            SubagentType.TABLE: MockSubgraphBuilder(SubagentType.TABLE, delay=delay),
            SubagentType.REFERENCE: MockSubgraphBuilder(SubagentType.REFERENCE, delay=delay),
        }

        selected = ["search", "table", "reference"]

        # 测试顺序执行时间
        start_time = time.time()
        sequential_results = []
        for type_value in selected:
            agent_type = SubagentType(type_value)
            result = await builders[agent_type].invoke("查询", "test", {})
            sequential_results.append(result)
        sequential_duration = time.time() - start_time

        # 重置计数器
        for builder in builders.values():
            builder.invoke_count = 0

        # 测试并发执行时间
        start_time = time.time()
        tasks = [
            builders[SubagentType(type_value)].invoke("查询", "test", {})
            for type_value in selected
        ]
        parallel_results = await asyncio.gather(*tasks)
        parallel_duration = time.time() - start_time

        # 验证
        assert len(sequential_results) == len(parallel_results)
        # 并发执行应显著快于顺序执行
        assert parallel_duration < sequential_duration * 0.7
        # 顺序执行时间约为 3 * delay，并发约为 1 * delay
        assert sequential_duration >= 3 * delay * 0.9  # 允许10%误差
        assert parallel_duration < 3 * delay * 0.5  # 并发应小于顺序的50%


class TestConcurrentExecutionErrorHandling:
    """测试并发执行错误处理"""

    @pytest.mark.asyncio
    async def test_parallel_execution_with_partial_failure(self):
        """测试并发执行时部分子智能体失败"""
        # 创建 Mock 子图构建器（一个失败，两个成功）
        search_builder = MockSubgraphBuilder(SubagentType.SEARCH, delay=0.05)
        table_builder = MockSubgraphBuilder(
            SubagentType.TABLE,
            delay=0.05,
            should_fail=True
        )
        reference_builder = MockSubgraphBuilder(SubagentType.REFERENCE, delay=0.05)

        selected = ["search", "table", "reference"]
        builders = {
            SubagentType.SEARCH: search_builder,
            SubagentType.TABLE: table_builder,
            SubagentType.REFERENCE: reference_builder,
        }

        # 并发执行（使用 return_exceptions=True）
        tasks = [
            builders[SubagentType(type_value)].invoke("查询", "test", {})
            for type_value in selected
        ]
        outputs = await asyncio.gather(*tasks, return_exceptions=True)

        # 验证
        assert len(outputs) == 3
        assert isinstance(outputs[0], dict)  # search 成功
        assert isinstance(outputs[1], Exception)  # table 失败
        assert isinstance(outputs[2], dict)  # reference 成功

        # 成功的结果应包含内容
        assert "content" in outputs[0]
        assert "content" in outputs[2]

    @pytest.mark.asyncio
    async def test_parallel_execution_with_all_failures(self):
        """测试所有子智能体都失败的情况"""
        # 创建全部失败的 Mock 子图构建器
        builders = [
            MockSubgraphBuilder(SubagentType.SEARCH, delay=0.05, should_fail=True),
            MockSubgraphBuilder(SubagentType.TABLE, delay=0.05, should_fail=True),
        ]

        selected = ["search", "table"]

        # 并发执行
        tasks = [builder.invoke("查询", "test", {}) for builder in builders]
        outputs = await asyncio.gather(*tasks, return_exceptions=True)

        # 验证所有结果都是异常
        assert len(outputs) == 2
        assert all(isinstance(o, Exception) for o in outputs)

    @pytest.mark.asyncio
    async def test_parallel_execution_error_isolation(self):
        """测试并发执行时错误隔离（一个失败不影响其他）"""
        success_count = 0
        failure_count = 0

        async def mock_invoke(should_fail: bool):
            await asyncio.sleep(0.05)
            if should_fail:
                raise RuntimeError("Intentional failure")
            return {"success": True}

        # 并发执行：一个成功，一个失败
        tasks = [
            mock_invoke(False),  # 成功
            mock_invoke(True),   # 失败
        ]
        outputs = await asyncio.gather(*tasks, return_exceptions=True)

        # 验证
        for output in outputs:
            if isinstance(output, Exception):
                failure_count += 1
            else:
                success_count += 1

        assert success_count == 1
        assert failure_count == 1


class TestConcurrentExecutionResultAggregation:
    """测试并发执行结果聚合"""

    @pytest.mark.asyncio
    async def test_parallel_result_aggregation(self):
        """测试并发执行结果的正确聚合"""
        # 创建不同内容的 Mock 子图
        builders = {
            SubagentType.SEARCH: MockSubgraphBuilder(
                SubagentType.SEARCH,
                content="搜索结果：母线失压处理"
            ),
            SubagentType.TABLE: MockSubgraphBuilder(
                SubagentType.TABLE,
                content="表格结果：表6-2"
            ),
            SubagentType.REFERENCE: MockSubgraphBuilder(
                SubagentType.REFERENCE,
                content="引用结果：见第六章"
            ),
        }

        selected = ["search", "table", "reference"]

        # 并发执行
        tasks = [
            builders[SubagentType(type_value)].invoke("查询", "test", {})
            for type_value in selected
        ]
        outputs = await asyncio.gather(*tasks)

        # 验证结果独立性
        contents = [o["content"] for o in outputs]
        assert len(contents) == 3
        assert len(set(contents)) == 3  # 所有内容不同
        assert any("搜索" in c for c in contents)
        assert any("表格" in c for c in contents)
        assert any("引用" in c for c in contents)

    @pytest.mark.asyncio
    async def test_parallel_source_collection(self):
        """测试并发执行来源收集"""
        # 创建返回不同来源的 Mock 子图
        builders = {
            SubagentType.SEARCH: MockSubgraphBuilder(
                SubagentType.SEARCH,
                content="搜索结果"
            ),
            SubagentType.TABLE: MockSubgraphBuilder(
                SubagentType.TABLE,
                content="表格结果"
            ),
        }

        # 修改返回的 sources
        original_invoke_search = builders[SubagentType.SEARCH].invoke
        original_invoke_table = builders[SubagentType.TABLE].invoke

        async def custom_invoke_search(query, reg_id, hints):
            result = await original_invoke_search(query, reg_id, hints)
            result["sources"] = ["test_reg:p10", "test_reg:p11"]
            return result

        async def custom_invoke_table(query, reg_id, hints):
            result = await original_invoke_table(query, reg_id, hints)
            result["sources"] = ["test_reg:p20", "test_reg:p21"]
            return result

        builders[SubagentType.SEARCH].invoke = custom_invoke_search
        builders[SubagentType.TABLE].invoke = custom_invoke_table

        selected = ["search", "table"]

        # 并发执行
        tasks = [
            builders[SubagentType(type_value)].invoke("查询", "test", {})
            for type_value in selected
        ]
        outputs = await asyncio.gather(*tasks)

        # 收集所有来源
        all_sources = []
        for output in outputs:
            all_sources.extend(output["sources"])

        # 验证
        assert len(all_sources) == 4
        assert "test_reg:p10" in all_sources
        assert "test_reg:p11" in all_sources
        assert "test_reg:p20" in all_sources
        assert "test_reg:p21" in all_sources


class TestConcurrentExecutionContextPassing:
    """测试并发执行上下文传递"""

    @pytest.mark.asyncio
    async def test_parallel_with_hints(self):
        """测试并发执行时提示信息传递"""
        # 创建 Mock 子图
        builders = {
            SubagentType.SEARCH: MockSubgraphBuilder(SubagentType.SEARCH),
            SubagentType.TABLE: MockSubgraphBuilder(SubagentType.TABLE),
        }

        hints = {
            "chapter_scope": "第六章",
            "table_hint": "表6-2",
            "section_number": "2.1.4",
        }

        selected = ["search", "table"]

        # 并发执行（传递 hints）
        tasks = [
            builders[SubagentType(type_value)].invoke("查询", "test", hints)
            for type_value in selected
        ]
        outputs = await asyncio.gather(*tasks)

        # 验证每个子图都收到相同的 hints
        for builder in builders.values():
            assert builder.invoke_count == 1
            assert len(builder.invoke_history) == 1
            assert builder.invoke_history[0]["hints"] == hints

    @pytest.mark.asyncio
    async def test_parallel_with_different_reg_ids(self):
        """测试不同规程ID的并发执行"""
        # 创建 Mock 子图
        builders = {
            SubagentType.SEARCH: MockSubgraphBuilder(SubagentType.SEARCH),
            SubagentType.TABLE: MockSubgraphBuilder(SubagentType.TABLE),
        }

        selected = ["search", "table"]

        # 并发执行（传递不同 reg_id）
        tasks = [
            builders[SubagentType.SEARCH].invoke("查询", "angui_2024", {}),
            builders[SubagentType.TABLE].invoke("查询", "wengui_2024", {}),
        ]
        outputs = await asyncio.gather(*tasks)

        # 验证每个子图收到正确的 reg_id
        assert builders[SubagentType.SEARCH].invoke_history[0]["reg_id"] == "angui_2024"
        assert builders[SubagentType.TABLE].invoke_history[0]["reg_id"] == "wengui_2024"


class TestConcurrentExecutionPerformance:
    """测试并发执行性能"""

    @pytest.mark.asyncio
    async def test_parallel_speedup_with_many_subagents(self):
        """测试多子智能体并发的加速效果"""
        # 创建多个子智能体
        num_subagents = 5
        delay = 0.03

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
        sequential_results = []
        for builder in builders:
            result = await builder.invoke("查询", "test", {})
            sequential_results.append(result)
        sequential_time = time.time() - start_time

        # 重置
        for builder in builders:
            builder.invoke_count = 0

        # 并发执行
        start_time = time.time()
        parallel_results = await asyncio.gather(*[
            builder.invoke("查询", "test", {}) for builder in builders
        ])
        parallel_time = time.time() - start_time

        # 验证
        assert len(sequential_results) == num_subagents
        assert len(parallel_results) == num_subagents

        # 并发应显著快于顺序
        speedup = sequential_time / parallel_time
        assert speedup >= 2.0  # 至少2倍加速

    @pytest.mark.asyncio
    async def test_parallel_execution_overhead(self):
        """测试并发执行的开销"""
        # 创建快速执行的子图（最小延迟）
        builders = [
            MockSubgraphBuilder(SubagentType.SEARCH, delay=0.001)
            for _ in range(2)
        ]

        # 并发执行
        start_time = time.time()
        _ = await asyncio.gather(*[
            builder.invoke("查询", "test", {}) for builder in builders
        ])
        parallel_time = time.time() - start_time

        # 验证并发开销合理（应小于50ms）
        assert parallel_time < 0.05


# ============================================================================
# Integration Tests (with real LangGraph orchestrator if available)
# ============================================================================


class TestConcurrentExecutionIntegration:
    """集成测试（需要真实的 LangGraph 环境）"""

    @pytest.mark.skipif(
        True,  # 默认跳过，需要真实环境时设置为 False
        reason="Requires real LangGraph and MCP setup"
    )
    @pytest.mark.asyncio
    async def test_real_parallel_execution(self):
        """测试真实环境的并发执行"""
        # 此测试需要：
        # 1. 真实的 MCP Server
        # 2. 真实的 LLM API
        # 3. 已加载的规程文档
        pass

    @pytest.mark.skipif(
        True,
        reason="Requires real LangGraph and MCP setup"
    )
    @pytest.mark.asyncio
    async def test_real_vs_mock_consistency(self):
        """测试真实环境和 Mock 环境的结果一致性"""
        pass
