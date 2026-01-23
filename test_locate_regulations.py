#!/usr/bin/env python
"""测试 locate_regulations 功能"""

from regreader.mcp.tools import RegReaderTools
from regreader.storage import PageStore

def test_locate_regulations():
    """测试规程自动定位功能"""
    tools = RegReaderTools()

    # 测试查询
    test_queries = [
        "锦苏直流系统发生闭锁故障",
        "母线失压如何处理",
        "安控装置的动作逻辑",
    ]

    print("=" * 60)
    print("测试 locate_regulations 功能")
    print("=" * 60)

    for query in test_queries:
        print(f"\n查询: {query}")
        print("-" * 60)

        try:
            result = tools.locate_regulations(query, top_k=3, min_score=0.0)  # 降低阈值到 0.0

            print(f"总规程数: {result['total_regulations']}")
            print(f"匹配规程数: {len(result['matches'])}")

            for i, match in enumerate(result['matches'], 1):
                print(f"\n{i}. {match['title']}")
                print(f"   规程ID: {match['reg_id']}")
                print(f"   相关度: {match['score']:.2f} ({match.get('confidence_level', 'unknown')})")
                print(f"   匹配原因: {match['match_reason']}")
                if match['keywords']:
                    print(f"   匹配关键词: {', '.join(match['keywords'])}")

        except Exception as e:
            print(f"错误: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_locate_regulations()
