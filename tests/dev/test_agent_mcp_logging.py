"""对比测试三个 Agent 的 MCP 日志行为

验证 ClaudeAgent 的 debug_stderr 与其他两个 Agent 的差异。
"""

import asyncio
import sys

# 添加日志拦截
original_stderr = sys.stderr


class StderrCapture:
    """捕获 stderr 输出"""

    def __init__(self):
        self.lines = []
        self.original = sys.stderr

    def write(self, text):
        if text.strip():
            self.lines.append(text)
        self.original.write(text)

    def flush(self):
        self.original.flush()


async def test_claude_agent():
    """测试 ClaudeAgent 的 MCP 日志"""
    from grid_code.agents import ClaudeAgent
    from grid_code.agents.mcp_connection import MCPConnectionConfig

    print("\n=== Testing ClaudeAgent ===", file=sys.stderr)

    config = MCPConnectionConfig.stdio()
    agent = ClaudeAgent(
        reg_id="angui_2024",
        mcp_config=config,
    )

    # 发送简单查询
    try:
        response = await agent.chat("列出所有规程")
        print(f"Response length: {len(response.content)}", file=sys.stderr)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)


async def test_pydantic_agent():
    """测试 PydanticAIAgent 的 MCP 日志"""
    from grid_code.agents import PydanticAIAgent
    from grid_code.agents.mcp_connection import MCPConnectionConfig

    print("\n=== Testing PydanticAIAgent ===", file=sys.stderr)

    config = MCPConnectionConfig.stdio()

    async with PydanticAIAgent(
        reg_id="angui_2024",
        mcp_config=config,
    ) as agent:
        try:
            response = await agent.chat("列出所有规程")
            print(f"Response length: {len(response.content)}", file=sys.stderr)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)


async def test_langgraph_agent():
    """测试 LangGraphAgent 的 MCP 日志"""
    from grid_code.agents import LangGraphAgent
    from grid_code.agents.mcp_connection import MCPConnectionConfig

    print("\n=== Testing LangGraphAgent ===", file=sys.stderr)

    config = MCPConnectionConfig.stdio()

    async with LangGraphAgent(
        reg_id="angui_2024",
        mcp_config=config,
    ) as agent:
        try:
            response = await agent.chat("列出所有规程")
            print(f"Response length: {len(response.content)}", file=sys.stderr)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)


async def main():
    """运行测试"""
    print("Comparing MCP logging behavior across agents...", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    # 测试每个 Agent
    # await test_claude_agent()  # ClaudeAgent 需要 ANTHROPIC_API_KEY
    await test_pydantic_agent()
    await test_langgraph_agent()


if __name__ == "__main__":
    asyncio.run(main())
