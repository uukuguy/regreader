#!/usr/bin/env python
"""表格注册表统计脚本

显示指定规程的表格注册表统计信息。

Usage:
    python scripts/makefile/table_registry_stats.py <reg_id>
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from grid_code.storage import PageStore


def show_stats(reg_id: str) -> None:
    """显示表格注册表统计信息

    Args:
        reg_id: 规程标识符（如 angui_2024）
    """
    ps = PageStore()
    reg = ps.load_table_registry(reg_id)

    if reg:
        print(f"Table Registry Statistics for {reg_id}:")
        print(f"  Total tables: {reg.total_tables}")
        print(f"  Cross-page tables: {reg.cross_page_tables}")
        print(f"  Segment mappings: {len(reg.segment_to_table)}")
    else:
        print(f"No table registry found for {reg_id}")


def main() -> int:
    """主函数"""
    if len(sys.argv) != 2:
        print("Usage: python scripts/makefile/table_registry_stats.py <reg_id>")
        print("\nExample:")
        print("  python scripts/makefile/table_registry_stats.py angui_2024")
        return 1

    reg_id = sys.argv[1]

    try:
        show_stats(reg_id)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
