"""测试异步上下文中的 MCP 适配器

验证在 asyncio.run() 内部调用 MCP 工具时的事件循环处理
"""

import asyncio
import pytest
from regreader.mcp.adapter import RegReaderMCPToolsAdapter


def test_mcp_adapter_in_async_context():
    """测试在异步上下文中使用 MCP 适配器"""

    async def async_operation():
        """在异步函数中调用 MCP 工具"""
        # 创建适配器（stdio 模式，会自动启动子进程）
        adapter = RegReaderMCPToolsAdapter(transport="stdio")

        try:
            # 在异步上下文中调用工具（不应该抛出 asyncio.run() 错误）
            result = adapter.list_regulations()
            assert result is not None
            assert isinstance(result, list)
            return len(result)
        finally:
            # 清理（使用同步方法）
            adapter.close()

    # 运行异步操作
    count = asyncio.run(async_operation())
    print(f"✓ 在异步上下文中成功调用 MCP 工具，返回 {count} 个规程")
    assert count > 0


def test_mcp_adapter_nested_async_calls():
    """测试嵌套异步调用"""

    async def nested_async_operation():
        """嵌套的异步操作"""
        adapter = RegReaderMCPToolsAdapter(transport="stdio")

        try:
            # 第一次调用
            result1 = adapter.list_regulations()
            print(f"✓ 第一次调用成功，返回 {len(result1)} 个规程")

            # 第二次调用（会话复用）
            result2 = adapter.list_regulations()
            print(f"✓ 第二次调用成功，返回 {len(result2)} 个规程")

            return True
        finally:
            adapter.close()

    result = asyncio.run(nested_async_operation())
    assert result is True


def test_mcp_adapter_sync_context():
    """测试在同步上下文中使用 MCP 适配器"""

    adapter = RegReaderMCPToolsAdapter(transport="stdio")

    try:
        # 在同步上下文中调用工具
        result = adapter.list_regulations()
        assert result is not None
        assert isinstance(result, list)
        print(f"✓ 在同步上下文中成功调用 MCP 工具，返回 {len(result)} 个规程")
    finally:
        adapter.close()


if __name__ == "__main__":
    # 运行测试
    print("=" * 60)
    print("测试 MCP 适配器的事件循环处理")
    print("=" * 60)

    print("\n[测试 1] 同步上下文")
    print("-" * 40)
    test_mcp_adapter_sync_context()

    print("\n[测试 2] 异步上下文")
    print("-" * 40)
    test_mcp_adapter_in_async_context()

    print("\n[测试 3] 嵌套异步调用")
    print("-" * 40)
    test_mcp_adapter_nested_async_calls()

    print("\n" + "=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)
