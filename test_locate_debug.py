#!/usr/bin/env python
"""调试 locate_regulations 功能"""

from regreader.storage import PageStore

def debug_matching():
    """调试匹配逻辑"""
    store = PageStore()
    regs = store.list_regulations()

    query = "锦苏直流系统发生闭锁故障"
    query_lower = query.lower()

    print(f"查询: {query}")
    print(f"查询（小写）: {query_lower}")
    print(f"查询词列表: {query_lower.split()}")
    print()

    for reg in regs:
        print(f"规程: {reg.reg_id}")
        print(f"  标题: {reg.title}")
        print(f"  关键词: {reg.keywords}")
        print()

        # 测试关键词匹配
        if reg.keywords:
            keywords_lower = [kw.lower() for kw in reg.keywords]
            print("  关键词匹配测试:")
            for kw in keywords_lower:
                # 方法1：关键词在查询中
                match1 = kw in query_lower
                # 方法2：查询词在关键词中
                query_words = [w for w in query_lower.split() if len(w) > 1]
                match2 = any(word in kw for word in query_words)

                print(f"    '{kw}':")
                print(f"      - 关键词在查询中: {match1}")
                print(f"      - 查询词在关键词中: {match2}")
                if match2:
                    matching_words = [w for w in query_words if w in kw]
                    print(f"      - 匹配的词: {matching_words}")
        print()

if __name__ == "__main__":
    debug_matching()
