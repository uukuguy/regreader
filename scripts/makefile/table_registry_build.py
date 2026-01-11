#!/usr/bin/env python
"""构建表格注册表脚本

用于将 Makefile 中的 Python 一行代码提取为独立脚本，提高可读性和可测试性。

Usage:
    python scripts/makefile/table_registry_build.py <reg_id>
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from grid_code.storage import PageStore
from grid_code.parser import TableRegistryBuilder


def build_table_registry(reg_id: str) -> None:
    """构建表格注册表

    Args:
        reg_id: 规程标识符（如 angui_2024）
    """
    ps = PageStore()

    # 加载规程信息
    info = ps.load_info(reg_id)

    # 加载所有页面
    print(f"Loading {info.total_pages} pages...")
    pages = [ps.load_page(reg_id, i) for i in range(1, info.total_pages + 1)]

    # 构建注册表
    print(f"Building table registry for {reg_id}...")
    builder = TableRegistryBuilder(reg_id)
    registry = builder.build(pages)

    # 保存
    ps.save_table_registry(registry)

    # 输出统计
    print(f"Done: {registry.total_tables} tables, {registry.cross_page_tables} cross-page")


def main() -> int:
    """主函数"""
    if len(sys.argv) != 2:
        print("Usage: python scripts/makefile/table_registry_build.py <reg_id>")
        print("\nExample:")
        print("  python scripts/makefile/table_registry_build.py angui_2024")
        return 1

    reg_id = sys.argv[1]

    try:
        build_table_registry(reg_id)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
