#!/usr/bin/env python
"""列出跨页表格脚本

列出指定规程中所有跨页表格的信息。

Usage:
    python scripts/makefile/list_cross_page_tables.py <reg_id>
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from regreader.storage import PageStore


def list_cross_page_tables(reg_id: str) -> None:
    """列出所有跨页表格

    Args:
        reg_id: 规程标识符（如 angui_2024）
    """
    ps = PageStore()
    reg = ps.load_table_registry(reg_id)

    if reg:
        cross_page_tables = [
            (tid, e) for tid, e in reg.tables.items() if e.is_cross_page
        ]

        if cross_page_tables:
            print(f"Cross-page tables in {reg_id}:")
            for tid, e in cross_page_tables:
                print(f"  {tid}: P{e.page_start}-{e.page_end} ({len(e.segments)} segments)")
            print(f"\nTotal: {len(cross_page_tables)} cross-page tables")
        else:
            print(f"No cross-page tables found in {reg_id}")
    else:
        print(f"No table registry found for {reg_id}")


def main() -> int:
    """主函数"""
    if len(sys.argv) != 2:
        print("Usage: python scripts/makefile/list_cross_page_tables.py <reg_id>")
        print("\nExample:")
        print("  python scripts/makefile/list_cross_page_tables.py angui_2024")
        return 1

    reg_id = sys.argv[1]

    try:
        list_cross_page_tables(reg_id)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
