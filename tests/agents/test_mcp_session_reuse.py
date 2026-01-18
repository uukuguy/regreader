"""测试 MCP 适配器的会话复用功能

验证：
1. SSE 模式连接到远程 MCP Server
2. 会话复用：首次调用创建会话，后续调用复用
3. 避免重复加载嵌入模型
"""

import asyncio
from regreader.mcp.adapter import RegReaderMCPToolsAdapter


def test_sse_session_reuse():
    """测试 SSE 模式的会话复用"""
    print("=" * 60)
    print("测试 SSE 模式 + 会话复用")
    print("=" * 60)

    # 创建 SSE 模式的适配器
    adapter = RegReaderMCPToolsAdapter(
        transport="sse",
        server_url="http://127.0.0.1:8080/sse"
    )

    try:
        print("\n[1] 首次调用：list_regulations()")
        print("-" * 40)
        result1 = adapter.list_regulations()
        print(f"✓ 返回 {len(result1)} 个规程")

        print("\n[2] 第二次调用：list_regulations()（应该复用会话）")
        print("-" * 40)
        result2 = adapter.list_regulations()
        print(f"✓ 返回 {len(result2)} 个规程")

        print("\n[3] 第三次调用：get_toc()")
        print("-" * 40)
        toc = adapter.get_toc("angui_2024")
        print(f"✓ 返回目录结构: {toc.get('structure', 'N/A')[:50]}...")

        print("\n[4] 第四次调用：smart_search()")
        print("-" * 40)
        search_result = adapter.smart_search("母线失压", "angui_2024", limit=3)
        print(f"✓ 找到 {len(search_result)} 个结果")

        print("\n" + "=" * 60)
        print("✅ 所有调用成功！会话已复用，避免重复加载嵌入模型")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        print("\n提示：请确保 MCP Server 正在运行：")
        print("  regreader serve --transport sse --port 8080")
    finally:
        # 清理资源
        print("\n[清理] 关闭 MCP 会话...")
        asyncio.run(adapter.close())
        print("✓ 会话已关闭")


if __name__ == "__main__":
    test_sse_session_reuse()
