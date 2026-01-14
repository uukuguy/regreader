"""测试 get_toc 深度限制功能

验证 get_toc 工具的 max_depth 和 expand_section 参数功能。
"""

import json

import pytest

from regreader.mcp.tools import RegReaderTools

# 测试用规程 ID
TEST_REG_ID = "angui_2024"


def count_toc_chars(toc: dict) -> int:
    """计算目录树的 JSON 字符数"""
    return len(json.dumps(toc, ensure_ascii=False))


def count_toc_nodes(toc: dict) -> int:
    """递归统计目录树中的节点数量"""
    count = 0
    for item in toc.get("items", []):
        count += 1 + count_nodes_in_item(item)
    return count


def count_nodes_in_item(item: dict) -> int:
    """递归统计单个目录项的节点数量"""
    count = 0
    for child in item.get("children", []):
        count += 1 + count_nodes_in_item(child)
    return count


def has_children_count_field(toc: dict) -> bool:
    """检查目录树中是否有被截断的节点（带 children_count 字段）"""
    for item in toc.get("items", []):
        if check_children_count(item):
            return True
    return False


def check_children_count(item: dict) -> bool:
    """递归检查单个目录项是否有 children_count 字段"""
    if "children_count" in item and item.get("children_count", 0) > 0:
        return True
    for child in item.get("children", []):
        if check_children_count(child):
            return True
    return False


class TestGetTocDepth:
    """测试 get_toc 深度限制功能"""

    @pytest.fixture
    def tools(self):
        """获取工具实例"""
        return RegReaderTools()

    def test_default_depth(self, tools):
        """测试默认深度（3级）返回合理大小"""
        result = tools.get_toc(TEST_REG_ID)

        char_count = count_toc_chars(result)
        print(f"\n默认深度返回字符数: {char_count}")

        # 默认深度应该返回合理大小（< 30000 字符）
        assert char_count < 30000, f"默认深度返回过大: {char_count} 字符"

    def test_depth_1(self, tools):
        """测试深度 1 级返回最简洁的概览"""
        result = tools.get_toc(TEST_REG_ID, max_depth=1)

        char_count = count_toc_chars(result)
        print(f"\n深度1返回字符数: {char_count}")

        # 深度 1 应该非常小
        assert char_count < 5000, f"深度1返回过大: {char_count} 字符"

        # 应该有被截断的节点
        assert has_children_count_field(result), "深度1应该有被截断的节点"

    def test_depth_2(self, tools):
        """测试深度 2 级"""
        result = tools.get_toc(TEST_REG_ID, max_depth=2)

        char_count = count_toc_chars(result)
        print(f"\n深度2返回字符数: {char_count}")

        # 深度 2 应该适中
        assert char_count < 10000, f"深度2返回过大: {char_count} 字符"

    def test_depth_comparison(self, tools):
        """测试不同深度返回大小的递增关系"""
        depth_1 = count_toc_chars(tools.get_toc(TEST_REG_ID, max_depth=1))
        depth_2 = count_toc_chars(tools.get_toc(TEST_REG_ID, max_depth=2))
        depth_3 = count_toc_chars(tools.get_toc(TEST_REG_ID, max_depth=3))

        print(f"\n深度对比: 1级={depth_1}, 2级={depth_2}, 3级={depth_3}")

        # 验证递增关系
        assert depth_1 < depth_2 < depth_3, "深度应该递增"

    def test_expand_section(self, tools):
        """测试展开特定章节分支"""
        # 获取默认深度的结果
        default_result = tools.get_toc(TEST_REG_ID, max_depth=2)

        # 展开 "2" 章节
        expanded_result = tools.get_toc(TEST_REG_ID, max_depth=2, expand_section="2")

        default_chars = count_toc_chars(default_result)
        expanded_chars = count_toc_chars(expanded_result)

        print(f"\n展开章节对比: 默认={default_chars}, 展开2={expanded_chars}")

        # 展开后应该更大
        assert expanded_chars > default_chars, "展开章节后应该返回更多内容"

    def test_full_depth(self, tools):
        """测试完整深度（6级）"""
        result = tools.get_toc(TEST_REG_ID, max_depth=6)

        char_count = count_toc_chars(result)
        print(f"\n完整深度返回字符数: {char_count}")

        # 完整深度应该很大
        assert char_count > 50000, f"完整深度应该返回大量内容: {char_count} 字符"

        # 完整深度不应该有被截断的节点
        assert not has_children_count_field(result), "完整深度不应该有被截断的节点"

    def test_result_structure(self, tools):
        """测试返回结果的结构"""
        result = tools.get_toc(TEST_REG_ID, max_depth=2)

        # 验证顶级字段
        assert "reg_id" in result
        assert "title" in result
        assert "total_pages" in result
        assert "items" in result
        assert isinstance(result["items"], list)

        # 验证目录项结构
        if result["items"]:
            item = result["items"][0]
            assert "title" in item
            assert "level" in item
            assert "page_start" in item
            assert "children" in item


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
