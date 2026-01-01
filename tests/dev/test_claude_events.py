"""Test Claude Agent SDK events to understand what's being sent."""
import asyncio
import sys
from loguru import logger

async def test_events():
    """Run a simple query and log all events."""
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ClaudeSDKClient,
        ResultMessage,
        TextBlock,
        ThinkingBlock,
        ToolUseBlock,
        ToolResultBlock,
    )

    # Configure logging to see all events
    logger.remove()
    logger.add(lambda msg: print(msg), level="DEBUG")

    # 使用 MCP 工具配置
    mcp_config = {
        "gridcode": {
            "type": "stdio",
            "command": sys.executable,
            "args": ["-m", "grid_code.cli", "serve", "--transport", "stdio"],
        }
    }

    options = ClaudeAgentOptions(
        model="claude-sonnet-4-20250514",
        system_prompt="你是一个电力规程助手。使用 MCP 工具回答问题。",
        mcp_servers=mcp_config,
        allowed_tools=["mcp__gridcode__get_toc", "mcp__gridcode__smart_search"],
        max_turns=3,
        permission_mode="bypassPermissions",
        include_partial_messages=True,
    )

    print("=" * 60)
    print("Starting Claude Agent SDK event test with MCP tools...")
    print("=" * 60)

    async with ClaudeSDKClient(options=options) as client:
        await client.query("请获取 angui_2024 规程的目录结构")

        event_count = 0
        async for event in client.receive_response():
            event_count += 1
            event_type = type(event).__name__

            # 只打印关键事件
            if event_type in ["AssistantMessage", "ResultMessage"]:
                print(f"\n--- Event #{event_count}: {event_type} ---")
                if isinstance(event, AssistantMessage):
                    print(f"Content blocks: {len(event.content)}")
                    for i, block in enumerate(event.content):
                        block_type = type(block).__name__
                        print(f"  Block {i}: {block_type}")
                        if isinstance(block, ToolUseBlock):
                            print(f"    Tool: {block.name}")
                            print(f"    ID: {getattr(block, 'id', 'N/A')}")
                            print(f"    Input: {block.input}")
                        elif isinstance(block, ToolResultBlock):
                            print(f"    Tool ID: {getattr(block, 'tool_use_id', 'N/A')}")
                            content = getattr(block, 'content', None)
                            if content:
                                content_str = str(content)[:100]
                                print(f"    Content: {content_str}...")
                elif isinstance(event, ResultMessage):
                    result = event.result or ""
                    print(f"Result: {result[:200]}...")

            elif hasattr(event, 'event') and isinstance(getattr(event, 'event', None), dict):
                inner = event.event
                event_inner_type = inner.get('type', '')
                # 只打印工具相关的流式事件
                if 'tool' in event_inner_type or event_inner_type in ['content_block_start', 'content_block_stop']:
                    print(f"\n--- Event #{event_count}: StreamEvent ({event_inner_type}) ---")
                    if event_inner_type == 'content_block_start':
                        cb = inner.get('content_block', {})
                        print(f"  Content block type: {cb.get('type', 'unknown')}")
                        if cb.get('type') == 'tool_use':
                            print(f"    Tool: {cb.get('name', 'unknown')}")
                            print(f"    ID: {cb.get('id', 'unknown')}")
                    elif event_inner_type == 'content_block_delta':
                        delta = inner.get('delta', {})
                        delta_type = delta.get('type', '')
                        if 'tool' in delta_type or 'input' in delta_type:
                            print(f"  Delta type: {delta_type}")
                            print(f"  Delta: {delta}")

    print("\n" + "=" * 60)
    print(f"Total events received: {event_count}")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_events())
