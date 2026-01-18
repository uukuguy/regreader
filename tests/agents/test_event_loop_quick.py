"""快速测试事件循环处理

验证在异步上下文中调用 MCP 适配器不会出错
"""

import asyncio
import pytest
from regreader.mcp.adapter import RegReaderMCPToolsAdapter


def test_sync_context():
    """测试在同步上下文中使用 MCP 适配器"""
    adapter = RegReaderMCPToolsAdapter(transport="stdio")

    try:
        result = adapter.list_regulations()
        assert result is not None
        assert isinstance(result, list)
        print(f"✓ 同步上下文成功，返回 {len(result)} 个规程")
    finally:
        adapter.close()


def test_async_context():
    """测试在异步上下文中使用 MCP 适配器（核心测试）"""

    async def async_operation():
        """在异步函数中调用 MCP 工具"""
        adapter = RegReaderMCPToolsAdapter(transport="stdio")

        try:
            # 在异步上下文中调用工具
            # 这里不应该抛出 "asyncio.run() cannot be called from a running event loop" 错误
            result = adapter.list_regulations()
            assert result is not None
            return len(result)
        finally:
            adapter.close()

    # 运行异步操作
    count = asyncio.run(async_operation())
    print(f"✓ 异步上下文成功，返回 {count} 个规程")
    assert count > 0


if __name__ == "__main__":
    print("=" * 60)
    print("快速测试：MCP 适配器事件循环处理")
    print("=" * 60)

    print("\n[测试 1] 同步上下文")
    print("-" * 40)
    test_sync_context()

    print("\n[测试 2] 异步上下文（关键测试）")
    print("-" * 40)
    test_async_context()

    print("\n" + "=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)
