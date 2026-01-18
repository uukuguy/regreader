"""简单测试 SSE 模式（不在异步上下文中）"""

import sys
sys.path.insert(0, 'src')

from regreader.mcp.adapter import RegReaderMCPToolsAdapter

print("测试：SSE 模式（同步上下文）")
print("=" * 60)

print("\n[1] 创建适配器...")
adapter = RegReaderMCPToolsAdapter(
    transport="sse",
    server_url="http://127.0.0.1:8080/sse"
)
print("✓ 适配器创建成功")

print("\n[2] 调用 list_regulations()...")
result = adapter.list_regulations()
print(f"✓ 调用成功，返回 {len(result)} 个规程")

print("\n[3] 关闭适配器...")
adapter.close()
print("✓ 完成")

print("\n" + "=" * 60)
print("✅ 测试完成！")
print("=" * 60)
