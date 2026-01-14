"""测试三个 Agent 的 MCP 日志输出差异

验证 ClaudeAgent、PydanticAIAgent、LangGraphAgent
在工具调用时 MCP Server 端的日志行为。
"""

import asyncio
import sys


async def test_langgraph_mcp():
    """测试 LangGraph 的 MCP 连接"""
    from regreader.mcp.client import RegReaderMCPClient

    print("\n=== Testing LangGraph MCP Client ===", file=sys.stderr)

    async with RegReaderMCPClient(transport="stdio") as client:
        print(f"Connected, tools: {[t['name'] for t in client._tools_cache]}", file=sys.stderr)

        # 调用工具
        result = await client.call_tool("list_regulations", {})
        print(f"Result: {result}", file=sys.stderr)


async def test_pydantic_mcp():
    """测试 Pydantic AI 的 MCP 连接"""
    from pydantic_ai.mcp import MCPServerStdio

    print("\n=== Testing Pydantic AI MCPServerStdio ===", file=sys.stderr)

    # 创建 MCP Server
    mcp_server = MCPServerStdio(
        sys.executable,
        args=["-m", "grid_code.cli", "serve", "--transport", "stdio"],
    )

    # 进入上下文
    async with mcp_server:
        tools = await mcp_server.list_tools()
        print(f"Tools: {[t.name for t in tools]}", file=sys.stderr)


async def main():
    """运行测试"""
    print("Testing MCP logging behavior...", file=sys.stderr)

    # 测试 LangGraph
    try:
        await test_langgraph_mcp()
    except Exception as e:
        print(f"LangGraph test failed: {e}", file=sys.stderr)

    # 测试 Pydantic AI
    try:
        await test_pydantic_mcp()
    except Exception as e:
        print(f"Pydantic AI test failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
