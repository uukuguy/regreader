"""MCP 工具测试脚本

测试所有 MCP 工具是否正确工作。
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from regreader.mcp.tools import RegReaderTools
from loguru import logger


def test_list_regulations(tools: RegReaderTools):
    """测试 list_regulations 工具"""
    print("\n=== 测试 list_regulations ===")
    result = tools.list_regulations()
    print(f"规程数量: {len(result)}")
    for reg in result:
        print(f"  - {reg['reg_id']}: {reg['title']} ({reg['total_pages']} 页)")
    return len(result) > 0


def test_get_toc(tools: RegReaderTools, reg_id: str):
    """测试 get_toc 工具"""
    print(f"\n=== 测试 get_toc ({reg_id}) ===")
    result = tools.get_toc(reg_id)
    print(f"标题: {result['title']}")
    print(f"总页数: {result['total_pages']}")
    print(f"目录项数量: {len(result['items'])}")
    # 打印前几个目录项
    for item in result['items'][:5]:
        print(f"  - [{item['level']}] {item['title']} (P{item['page_start']})")
    return result['total_pages'] > 0


def test_get_chapter_structure(tools: RegReaderTools, reg_id: str):
    """测试 get_chapter_structure 工具"""
    print(f"\n=== 测试 get_chapter_structure ({reg_id}) ===")
    result = tools.get_chapter_structure(reg_id)
    print(f"总章节数: {result['total_chapters']}")
    print(f"根节点数: {len(result['root_nodes'])}")
    for node in result['root_nodes']:
        print(f"  - {node['section_number']} {node['title']} (L{node['level']}, P{node['page_num']}, {node['children_count']} 子章节)")
    return result['total_chapters'] > 0


def test_read_page_range(tools: RegReaderTools, reg_id: str):
    """测试 read_page_range 工具"""
    print(f"\n=== 测试 read_page_range ({reg_id}, P7-8) ===")
    result = tools.read_page_range(reg_id, 7, 8)
    print(f"页码范围: {result['start_page']}-{result['end_page']}")
    print(f"内容长度: {len(result['content_markdown'])} 字符")
    print(f"已合并表格: {result['has_merged_tables']}")
    print(f"内容预览:\n{result['content_markdown'][:300]}...")
    return len(result['content_markdown']) > 0


def test_read_chapter_content(tools: RegReaderTools, reg_id: str):
    """测试 read_chapter_content 工具"""
    print(f"\n=== 测试 read_chapter_content ({reg_id}, 2.1.1) ===")
    result = tools.read_chapter_content(reg_id, "2.1.1", include_children=False)
    print(f"章节编号: {result['section_number']}")
    print(f"章节标题: {result['title']}")
    print(f"完整路径: {' > '.join(result['full_path'])}")
    print(f"页码范围: P{result['page_range'][0]}-{result['page_range'][1]}")
    print(f"内容块数: {result['block_count']}")
    print(f"子章节数: {len(result['children'])}")
    print(f"内容长度: {len(result['content_markdown'])} 字符")
    return result['block_count'] > 0


def test_smart_search(tools: RegReaderTools, reg_id: str):
    """测试 smart_search 工具"""
    print(f"\n=== 测试 smart_search ({reg_id}, '复龙站') ===")
    result = tools.smart_search(
        query="复龙站安控装置",
        reg_id=reg_id,
        limit=5
    )
    print(f"搜索结果数: {len(result['results'])}")
    for i, item in enumerate(result['results'][:3]):
        print(f"  {i+1}. [P{item['page_num']}] {item['snippet'][:80]}...")
    return len(result['results']) > 0


def main():
    """运行所有测试"""
    reg_id = "angui_2024"

    print("=" * 60)
    print("RegReader MCP 工具测试")
    print("=" * 60)

    tools = RegReaderTools()

    results = {
        "list_regulations": test_list_regulations(tools),
        "get_toc": test_get_toc(tools, reg_id),
        "get_chapter_structure": test_get_chapter_structure(tools, reg_id),
        "read_page_range": test_read_page_range(tools, reg_id),
        "read_chapter_content": test_read_chapter_content(tools, reg_id),
        "smart_search": test_smart_search(tools, reg_id),
    }

    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    for name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")

    all_passed = all(results.values())
    print(f"\n总体结果: {'全部通过' if all_passed else '有测试失败'}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
