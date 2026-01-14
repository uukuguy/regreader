#!/usr/bin/env python
"""标题检测统计脚本"""

import sys
from collections import Counter

from regreader.storage import PageStore


def main():
    if len(sys.argv) != 2:
        print("Usage: python stats_headings.py <reg_id>")
        sys.exit(1)

    reg_id = sys.argv[1]

    ps = PageStore()
    total_headings = 0
    pages_with_chapters = 0
    heading_levels = Counter()

    for i in range(1, 151):
        try:
            page = ps.load_page(reg_id, i)
            headings = [b for b in page.content_blocks if b.block_type == "heading"]
            total_headings += len(headings)

            if page.chapter_path:
                pages_with_chapters += 1

            for h in headings:
                if h.heading_level:
                    heading_levels[h.heading_level] += 1
        except Exception:
            break

    print(f"总标题数量: {total_headings}")
    print(f"有章节信息的页面: {pages_with_chapters}")
    print(f"标题级别分布: {dict(heading_levels)}")


if __name__ == "__main__":
    main()
