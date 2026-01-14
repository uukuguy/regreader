"""测试 Rich Live 模式对 MCP 日志的影响

模拟 CLI 实际运行环境，验证 Rich Live 是否会影响 stderr 输出。
"""

import asyncio
import sys

from rich.console import Console
from rich.live import Live


async def test_with_rich_live():
    """在 Rich Live 模式下测试 MCP 日志"""
    from regreader.mcp.client import RegReaderMCPClient

    console = Console()

    print("\n=== Testing with Rich Live ===", file=sys.stderr)

    # 使用 Rich Live 模式（模拟 CLI 的 AgentStatusDisplay）
    with Live("[cyan]思考中...[/cyan]", console=console, transient=True) as live:
        async with RegReaderMCPClient(transport="stdio") as client:
            live.update("[cyan]MCP 连接成功[/cyan]")
            print(f"Connected, tools: {len(client._tools_cache)}", file=sys.stderr)

            # 调用工具
            live.update("[cyan]调用 list_regulations...[/cyan]")
            result = await client.call_tool("list_regulations", {})
            live.update(f"[green]完成，结果: {len(result)} 条[/green]")

    print("\n=== Rich Live test completed ===", file=sys.stderr)


async def test_without_rich_live():
    """不使用 Rich Live 模式测试 MCP 日志"""
    from regreader.mcp.client import RegReaderMCPClient

    print("\n=== Testing WITHOUT Rich Live ===", file=sys.stderr)

    async with RegReaderMCPClient(transport="stdio") as client:
        print(f"Connected, tools: {len(client._tools_cache)}", file=sys.stderr)

        # 调用工具
        result = await client.call_tool("list_regulations", {})
        print(f"Result: {len(result)} regulations", file=sys.stderr)

    print("\n=== No Rich Live test completed ===", file=sys.stderr)


async def main():
    """运行测试"""
    print("=" * 60, file=sys.stderr)
    print("Testing Rich Live impact on MCP stderr logging", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    # 先测试不使用 Rich Live
    await test_without_rich_live()

    print("\n" + "=" * 60, file=sys.stderr)

    # 然后测试使用 Rich Live
    await test_with_rich_live()


if __name__ == "__main__":
    asyncio.run(main())
