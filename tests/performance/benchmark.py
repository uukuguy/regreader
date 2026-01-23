"""性能基准测试

对比顺序模式和并行模式的性能差异。

使用方法:
    python tests/performance/benchmark.py --reg-id angui_2024 --agent claude
    python tests/performance/benchmark.py --all  # 测试所有查询
"""

import argparse
import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from regreader.agents.orchestrated.claude import ClaudeOrchestrator
from regreader.agents.shared.callbacks import NullCallback
from regreader.agents.shared.mcp_connection import MCPConnectionConfig
from regreader.core.config import get_settings

console = Console()


@dataclass
class BenchmarkResult:
    """基准测试结果"""

    query: str
    sequential_time: float
    parallel_time: float
    improvement: float  # 改进百分比
    sequential_subtasks: int
    parallel_batches: int
    error: str | None = None

    @property
    def speedup(self) -> float:
        """加速比"""
        if self.parallel_time == 0:
            return 0
        return self.sequential_time / self.parallel_time



# 标准测试查询集
TEST_QUERIES = {
    "simple": [
        "母线失压如何处理？",
        "高压设备的安全要求有哪些？",
    ],
    "complex": [
        "母线失压的处理流程是什么？相关表格有哪些？",
        "锦苏直流系统发生闭锁故障时，安控装置的动作逻辑是什么？",
    ],
    "multi_hop": [
        "第六章的所有表格和注释内容是什么？",
        "查找所有关于故障处理的章节，并提取相关表格数据。",
    ],
}


async def benchmark_query(
    query: str,
    reg_id: str,
    parallel: bool,
    mcp_config: MCPConnectionConfig | None = None,
    reuse_agent: ClaudeOrchestrator | None = None,
) -> tuple[float, int, ClaudeOrchestrator]:
    """执行单个查询的基准测试

    Args:
        query: 查询内容
        reg_id: 规程ID
        parallel: 是否启用并行模式
        mcp_config: MCP 配置
        reuse_agent: 复用的 agent 实例（避免重复创建 MCP 连接）

    Returns:
        (执行时间, 子任务数量, agent 实例)
    """
    start = time.time()

    # 复用 agent 或创建新的
    if reuse_agent is not None:
        agent = reuse_agent
        already_initialized = True
    else:
        agent = ClaudeOrchestrator(
            reg_id=reg_id,
            mcp_config=mcp_config,
            status_callback=NullCallback(),
            parallel_mode=parallel,
        )
        already_initialized = False

    try:
        if not already_initialized:
            await agent.__aenter__()

        response = await agent.chat(query)
        elapsed = time.time() - start

        # 从 agent 获取子任务数量（如果可用）
        subtask_count = getattr(agent, "_last_subtask_count", 0)

        return elapsed, subtask_count, agent
    except Exception as e:
        console.print(f"[red]查询失败: {e}[/red]")
        if not already_initialized and agent is not None:
            try:
                await agent.__aexit__(None, None, None)
            except:
                pass
        return 0.0, 0, agent



async def run_benchmark(
    queries: list[str],
    reg_id: str,
    mcp_config: MCPConnectionConfig | None = None,
) -> list[BenchmarkResult]:
    """运行基准测试

    Args:
        queries: 查询列表
        reg_id: 规程ID
        mcp_config: MCP 配置

    Returns:
        基准测试结果列表
    """
    results = []

    # 在 stdio 模式下，创建共享的 MCP 管理器
    from regreader.agents.shared.mcp_connection import get_mcp_manager

    if mcp_config and mcp_config.transport == "stdio":
        # stdio 模式：创建共享的 MCP 管理器
        shared_mcp_manager = get_mcp_manager(mcp_config)
        await shared_mcp_manager.connect()
        console.print("[yellow]使用共享 MCP 连接（stdio 模式）[/yellow]")
    else:
        shared_mcp_manager = None

    # 创建两个 agent 实例（顺序模式和并行模式各一个）
    seq_agent = None
    par_agent = None

    try:
        # 创建 agent 时传入共享的 MCP 管理器
        seq_agent = ClaudeOrchestrator(
            reg_id=reg_id,
            mcp_config=mcp_config,
            status_callback=NullCallback(),
            parallel_mode=False,
        )
        if shared_mcp_manager:
            seq_agent._mcp_manager = shared_mcp_manager

        par_agent = ClaudeOrchestrator(
            reg_id=reg_id,
            mcp_config=mcp_config,
            status_callback=NullCallback(),
            parallel_mode=True,
        )
        if shared_mcp_manager:
            par_agent._mcp_manager = shared_mcp_manager

        # 初始化 agents
        await seq_agent.__aenter__()
        await par_agent.__aenter__()
        for query in queries:
            console.print(f"\n[cyan]测试查询:[/cyan] {query[:50]}...")

            # 顺序模式
            console.print("  [yellow]顺序模式...[/yellow]")
            seq_time, seq_subtasks, _ = await benchmark_query(
                query, reg_id, parallel=False, mcp_config=mcp_config, reuse_agent=seq_agent
            )

            # 并行模式
            console.print("  [yellow]并行模式...[/yellow]")
            par_time, par_batches, _ = await benchmark_query(
                query, reg_id, parallel=True, mcp_config=mcp_config, reuse_agent=par_agent
            )

            # 计算改进
            if seq_time > 0 and par_time > 0:
                improvement = (seq_time - par_time) / seq_time * 100
            else:
                improvement = 0

            result = BenchmarkResult(
                query=query,
                sequential_time=seq_time,
                parallel_time=par_time,
                improvement=improvement,
                sequential_subtasks=seq_subtasks,
                parallel_batches=par_batches,
            )
            results.append(result)

            console.print(
                f"  [green]✓ 完成[/green] - 改进: {improvement:.1f}% "
                f"(顺序: {seq_time:.2f}s, 并行: {par_time:.2f}s)"
            )

        return results
    finally:
        # 清理 agent 连接
        if seq_agent is not None:
            try:
                await seq_agent.__aexit__(None, None, None)
            except Exception as e:
                console.print(f"[yellow]警告: 关闭顺序模式 agent 失败: {e}[/yellow]")

        if par_agent is not None:
            try:
                await par_agent.__aexit__(None, None, None)
            except Exception as e:
                console.print(f"[yellow]警告: 关闭并行模式 agent 失败: {e}[/yellow]")

        # 注意：stdio 模式下的共享 MCP 管理器不需要手动关闭
        # 因为它是通过子进程管理的，手动关闭会导致 asyncio 任务作用域冲突
        # 让它在程序退出时自动清理即可



def display_results(results: list[BenchmarkResult]):
    """展示基准测试结果

    Args:
        results: 基准测试结果列表
    """
    table = Table(title="性能基准测试结果")

    table.add_column("查询", style="cyan", no_wrap=False, width=40)
    table.add_column("顺序模式", justify="right", style="yellow")
    table.add_column("并行模式", justify="right", style="green")
    table.add_column("改进", justify="right", style="magenta")
    table.add_column("加速比", justify="right", style="blue")

    for result in results:
        query_short = result.query[:37] + "..." if len(result.query) > 40 else result.query
        table.add_row(
            query_short,
            f"{result.sequential_time:.2f}s",
            f"{result.parallel_time:.2f}s",
            f"{result.improvement:+.1f}%",
            f"{result.speedup:.2f}x",
        )

    console.print(table)

    # 统计摘要
    if results:
        avg_improvement = sum(r.improvement for r in results) / len(results)
        avg_speedup = sum(r.speedup for r in results) / len(results)

        console.print(f"\n[bold]统计摘要:[/bold]")
        console.print(f"  平均改进: [magenta]{avg_improvement:.1f}%[/magenta]")
        console.print(f"  平均加速比: [blue]{avg_speedup:.2f}x[/blue]")



async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="RegReader 性能基准测试")
    parser.add_argument(
        "--reg-id",
        "-r",
        default="angui_2024",
        help="规程ID（默认: angui_2024）",
    )
    parser.add_argument(
        "--query-type",
        "-t",
        choices=["simple", "complex", "multi_hop", "all"],
        default="simple",
        help="查询类型（默认: simple）",
    )
    parser.add_argument(
        "--mcp-transport",
        choices=["stdio", "sse"],
        default="sse",
        help="MCP 传输模式（默认: sse）",
    )
    parser.add_argument(
        "--mcp-port",
        type=int,
        default=8080,
        help="MCP SSE 端口（默认: 8080）",
    )

    args = parser.parse_args()

    # 配置 MCP
    settings = get_settings()
    if args.mcp_transport == "sse":
        server_url = f"http://{settings.mcp_host}:{args.mcp_port}/sse"
        mcp_config = MCPConnectionConfig(
            transport=args.mcp_transport,
            server_url=server_url,
        )
    else:
        mcp_config = MCPConnectionConfig(
            transport=args.mcp_transport,
        )

    # 选择测试查询
    if args.query_type == "all":
        queries = []
        for query_list in TEST_QUERIES.values():
            queries.extend(query_list)
    else:
        queries = TEST_QUERIES[args.query_type]

    console.print(f"[bold]RegReader 性能基准测试[/bold]")
    console.print(f"规程ID: {args.reg_id}")
    console.print(f"查询类型: {args.query_type}")
    console.print(f"查询数量: {len(queries)}")
    console.print(f"MCP 模式: {args.mcp_transport}")

    # 运行基准测试
    results = await run_benchmark(queries, args.reg_id, mcp_config)

    # 展示结果
    display_results(results)


if __name__ == "__main__":
    asyncio.run(main())
