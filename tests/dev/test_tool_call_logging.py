"""测试 MCP 工具调用时的日志输出

直接测试工具调用（不涉及 LLM），验证 CallToolRequest 日志是否可见。
"""

import asyncio
import sys


async def test_direct_tool_call():
    """直接测试 MCP 工具调用日志"""
    from regreader.mcp.client import RegReaderMCPClient

    print("\n=== Direct MCP Tool Call Test ===", file=sys.stderr)

    async with RegReaderMCPClient(transport="stdio") as client:
        print(f"Connected, tools: {[t['name'] for t in client._tools_cache]}", file=sys.stderr)

        # 直接调用工具，观察日志
        print("\n--- Calling list_regulations ---", file=sys.stderr)
        result1 = await client.call_tool("list_regulations", {})
        print(f"Result: {len(result1)} regulations", file=sys.stderr)

        print("\n--- Calling get_toc ---", file=sys.stderr)
        result2 = await client.call_tool("get_toc", {"reg_id": "angui_2024"})
        print(f"TOC result: {type(result2)}", file=sys.stderr)


async def test_pydantic_mcp_tool_call():
    """测试 Pydantic AI MCP 工具调用日志"""
    from pydantic_ai.mcp import MCPServerStdio

    print("\n=== Pydantic AI MCP Tool Call Test ===", file=sys.stderr)

    mcp_server = MCPServerStdio(
        sys.executable,
        args=["-m", "grid_code.cli", "serve", "--transport", "stdio"],
    )

    async with mcp_server:
        tools = await mcp_server.list_tools()
        print(f"Connected, tools: {[t.name for t in tools]}", file=sys.stderr)

        # 直接调用工具
        print("\n--- Calling list_regulations ---", file=sys.stderr)
        result = await mcp_server.call_tool("list_regulations", {})
        print(f"Result type: {type(result)}", file=sys.stderr)


async def main():
    """运行测试"""
    print("Testing MCP tool call logging...", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    # 测试 LangGraph MCP Client
    print("\n[Test 1: RegReaderMCPClient (LangGraph)]", file=sys.stderr)
    try:
        await test_direct_tool_call()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)

    # 测试 Pydantic AI MCP
    print("\n[Test 2: MCPServerStdio (Pydantic AI)]", file=sys.stderr)
    try:
        await test_pydantic_mcp_tool_call()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
