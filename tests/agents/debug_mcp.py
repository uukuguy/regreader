"""调试 MCP 适配器"""

import sys
sys.path.insert(0, 'src')

from regreader.mcp.adapter import RegReaderMCPToolsAdapter
import traceback

print("=" * 60)
print("调试：MCP 适配器同步上下文测试")
print("=" * 60)

print("\n[步骤 1] 创建适配器...")
adapter = RegReaderMCPToolsAdapter(transport="stdio")
print("✓ 适配器创建成功")

print("\n[步骤 2] 调用 list_regulations()...")
try:
    result = adapter.list_regulations()
    print(f"✓ 调用成功，返回 {len(result)} 个规程")
    print(f"  第一个规程: {result[0] if result else '无'}")
except Exception as e:
    print(f"✗ 调用失败: {e}")
    traceback.print_exc()

print("\n[步骤 3] 关闭适配器...")
adapter.close()
print("✓ 适配器已关闭")

print("\n" + "=" * 60)
print("✅ 测试完成")
print("=" * 60)
