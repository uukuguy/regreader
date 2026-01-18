"""简单测试 MCP SSE 连接"""

import sys
sys.path.insert(0, 'src')

from regreader.mcp.adapter import RegReaderMCPToolsAdapter

print("测试 MCP SSE 适配器")
print("=" * 60)

print("\n[1] 创建适配器...")
adapter = RegReaderMCPToolsAdapter(
    transport="sse",
    server_url="http://127.0.0.1:8080/sse"
)
print("✓ 适配器创建成功")

print("\n[2] 调用 get_toc...")
try:
    result = adapter.get_toc("angui_2024")
    print(f"✓ 调用成功！")
    print(f"结果类型: {type(result)}")
    print(f"结果内容: {str(result)[:200]}")
except Exception as e:
    print(f"✗ 调用失败: {e}")
    import traceback
    traceback.print_exc()

print("\n[3] 关闭适配器...")
adapter.close()
print("✓ 完成")

print("\n" + "=" * 60)
