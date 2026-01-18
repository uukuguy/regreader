"""调试 MCP 适配器 SSE 模式"""

import sys
sys.path.insert(0, 'src')

from regreader.mcp.adapter import RegReaderMCPToolsAdapter
import traceback

print("=" * 60)
print("调试：MCP 适配器 SSE 模式测试")
print("=" * 60)

print("\n[步骤 1] 创建适配器 (SSE)...")
adapter = RegReaderMCPToolsAdapter(
    transport="sse",
    server_url="http://127.0.0.1:8080/sse"
)
print("✓ 适配器创建成功")

print("\n[步骤 2] 调用 list_regulations()...")
try:
    result = adapter.list_regulations()
    print(f"✓ 调用成功，返回 {len(result)} 个规程")
    if result:
        print(f"  第一个规程: {result[0].get('reg_id', 'N/A')}")
except Exception as e:
    print(f"✗ 调用失败: {e}")
    traceback.print_exc()

print("\n[步骤 3] 关闭适配器...")
adapter.close()
print("✓ 适配器已关闭")

print("\n" + "=" * 60)
print("✅ 测试完成")
print("=" * 60)
