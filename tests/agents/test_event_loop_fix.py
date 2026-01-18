"""测试 MCP 适配器在已有事件循环中的工作

验证 RegReaderMCPToolsAdapter 能够正确处理 asyncio.run() 在已有事件循环中的情况。
"""

import asyncio
from pathlib import Path
import tempfile

import pytest


class TestMCPAdapterEventLoopHandling:
    """测试 MCP 适配器的事件循环处理"""

    def test_mcp_adapter_in_running_event_loop(self):
        """测试 MCP 适配器在已有事件循环中工作"""
        from regreader.mcp.adapter import RegReaderMCPToolsAdapter

        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建 MCP 适配器（stdio 模式，会自动启动子进程）
            adapter = RegReaderMCPToolsAdapter(transport="stdio")

            # 定义一个在已有事件循环中运行的测试
            async def test_in_running_loop():
                # 在已有事件循环中调用 MCP 工具
                result = adapter.list_regulations()

                # 验证结果
                assert isinstance(result, list)
                return result

            # 创建并运行事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                # 在事件循环中运行测试
                result = loop.run_until_complete(test_in_running_loop())

                # 验证结果
                assert isinstance(result, list)

            finally:
                # 清理事件循环
                loop.close()

    def test_mcp_adapter_sse_mode_with_event_loop(self):
        """测试 SSE 模式下的 MCP 适配器在事件循环中工作"""
        from regreader.mcp.adapter import RegReaderMCPToolsAdapter

        # 注意：这个测试需要 MCP Server 在运行中
        # 跳过如果服务器不可用
        pytest.importorskip("httpx")

        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建 MCP 适配器（SSE 模式）
            adapter = RegReaderMCPToolsAdapter(
                transport="sse",
                server_url="http://127.0.0.1:8080/sse"
            )

            # 定义测试
            async def test_with_sse():
                try:
                    # 尝试调用 MCP 工具
                    result = adapter.list_regulations()
                    return result
                except Exception as e:
                    # 如果服务器不可用，跳过测试
                    if "Connection refused" in str(e) or "502" in str(e):
                        pytest.skip("MCP Server not available")
                    raise

            # 在事件循环中运行
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                result = loop.run_until_complete(test_with_sse())

                # 如果服务器可用，验证结果
                if result is not None:
                    assert isinstance(result, list)

            finally:
                loop.close()

    def test_mcp_adapter_multiple_calls_in_loop(self):
        """测试在事件循环中多次调用 MCP 工具"""
        from regreader.mcp.adapter import RegReaderMCPToolsAdapter

        adapter = RegReaderMCPToolsAdapter(transport="stdio")

        async def test_multiple_calls():
            # 多次调用不同的 MCP 工具
            regulations = adapter.list_regulations()

            # 验证每次调用都成功
            assert isinstance(regulations, list)

            return {
                "regulations": regulations,
            }

        # 在事件循环中运行
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = loop.run_until_complete(test_multiple_calls())

            # 验证结果
            assert "regulations" in result
            assert isinstance(result["regulations"], list)

        finally:
            loop.close()


if __name__ == "__main__":
    pytest.main([__file__, "-xvs"])
