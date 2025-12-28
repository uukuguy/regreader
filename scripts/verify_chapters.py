#!/usr/bin/env python
"""验证章节路径提取脚本"""

import sys

from grid_code.storage import PageStore


def main():
    if len(sys.argv) != 3:
        print("Usage: python verify_chapters.py <reg_id> <page_num>")
        sys.exit(1)

    reg_id = sys.argv[1]
    page_num = int(sys.argv[2])

    ps = PageStore()
    page = ps.load_page(reg_id, page_num)

    chapter_str = " > ".join(page.chapter_path) if page.chapter_path else "(无章节信息)"
    heading_blocks = [b for b in page.content_blocks if b.block_type == "heading"]

    print(f"章节路径: {chapter_str}")
    print(f"标题块数量: {len(heading_blocks)}")

    if heading_blocks:
        print("前3个标题:")
        for h in heading_blocks[:3]:
            print(f"  - {h.content_markdown[:60]}")


if __name__ == "__main__":
    main()
