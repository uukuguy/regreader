"""测试章节导出功能（基于内容块过滤）"""

import pytest
from unittest.mock import Mock, MagicMock
from regreader.services.export_service import ExportService
from regreader.storage.models import (
    ChapterNode,
    ContentBlock,
    DocumentStructure,
    ExportConfig,
    PageDocument,
    RegulationInfo,
)


@pytest.fixture
def mock_page_store():
    """创建模拟的 PageStore"""
    store = Mock()

    # 模拟 load_info
    store.load_info.return_value = RegulationInfo(
        reg_id="test_reg",
        title="测试规程",
        source_file="test.pdf",
        total_pages=10,
        indexed_at="2024-01-01T00:00:00",
    )

    return store


@pytest.fixture
def mock_doc_structure():
    """创建模拟的文档结构"""
    # 创建章节节点
    root_node = ChapterNode(
        node_id="node_1",
        section_number="2.1",
        title="第一章",
        level=1,
        page_num=1,
        children_ids=["node_2", "node_3"],
    )

    child_node_1 = ChapterNode(
        node_id="node_2",
        section_number="2.1.1",
        title="第一节",
        level=2,
        page_num=2,
        parent_id="node_1",
        children_ids=[],
    )

    child_node_2 = ChapterNode(
        node_id="node_3",
        section_number="2.1.2",
        title="第二节",
        level=2,
        page_num=3,
        parent_id="node_1",
        children_ids=[],
    )

    doc_structure = DocumentStructure(
        reg_id="test_reg",
        all_nodes={
            "node_1": root_node,
            "node_2": child_node_1,
            "node_3": child_node_2,
        },
        root_node_ids=["node_1"],
    )

    return doc_structure


@pytest.fixture
def mock_pages_with_blocks():
    """创建包含内容块的模拟页面"""
    pages = []

    # 第1页：包含 node_1 的内容
    page1 = PageDocument(
        reg_id="test_reg",
        page_num=1,
        content_blocks=[
            ContentBlock(
                block_id="test_reg_1_0",
                block_type="heading",
                order_in_page=0,
                content_markdown="## 2.1 第一章",
                chapter_node_id="node_1",
            ),
            ContentBlock(
                block_id="test_reg_1_1",
                block_type="text",
                order_in_page=1,
                content_markdown="这是第一章的内容。",
                chapter_node_id="node_1",
            ),
        ],
    )
    pages.append(page1)

    # 第2页：包含 node_2 的内容
    page2 = PageDocument(
        reg_id="test_reg",
        page_num=2,
        content_blocks=[
            ContentBlock(
                block_id="test_reg_2_0",
                block_type="heading",
                order_in_page=0,
                content_markdown="### 2.1.1 第一节",
                chapter_node_id="node_2",
            ),
            ContentBlock(
                block_id="test_reg_2_1",
                block_type="text",
                order_in_page=1,
                content_markdown="这是第一节的内容。",
                chapter_node_id="node_2",
            ),
        ],
    )
    pages.append(page2)

    # 第3页：包含 node_3 的内容和其他章节的内容
    page3 = PageDocument(
        reg_id="test_reg",
        page_num=3,
        content_blocks=[
            ContentBlock(
                block_id="test_reg_3_0",
                block_type="heading",
                order_in_page=0,
                content_markdown="### 2.1.2 第二节",
                chapter_node_id="node_3",
            ),
            ContentBlock(
                block_id="test_reg_3_1",
                block_type="text",
                order_in_page=1,
                content_markdown="这是第二节的内容。",
                chapter_node_id="node_3",
            ),
            ContentBlock(
                block_id="test_reg_3_2",
                block_type="text",
                order_in_page=2,
                content_markdown="这是其他章节的内容（不应该被导出）。",
                chapter_node_id="node_other",
            ),
        ],
    )
    pages.append(page3)

    return pages


def test_collect_chapter_blocks_without_children(
    mock_page_store, mock_doc_structure, mock_pages_with_blocks
):
    """测试收集章节内容块（不包含子章节）"""
    service = ExportService(mock_page_store)

    # 模拟 load_page
    mock_page_store.load_page.side_effect = lambda reg_id, page_num: mock_pages_with_blocks[page_num - 1]

    # 收集 node_2 的内容块（不包含子章节）
    chapter_node = mock_doc_structure.all_nodes["node_2"]
    blocks_with_pages, page_nums = service._collect_chapter_blocks(
        reg_id="test_reg",
        chapter_node=chapter_node,
        doc_structure=mock_doc_structure,
        include_children=False,
    )

    # 验证结果
    assert len(blocks_with_pages) == 2, "应该收集到2个内容块"
    assert page_nums == {2}, "应该只涉及第2页"
    # 验证所有块都属于 node_2
    for block, page_num in blocks_with_pages:
        assert block.chapter_node_id == "node_2", f"块 {block.block_id} 应该属于 node_2"
        assert page_num == 2, f"块 {block.block_id} 应该在第2页"


def test_collect_chapter_blocks_with_children(
    mock_page_store, mock_doc_structure, mock_pages_with_blocks
):
    """测试收集章节内容块（包含子章节）"""
    service = ExportService(mock_page_store)

    # 模拟 load_page
    mock_page_store.load_page.side_effect = lambda reg_id, page_num: mock_pages_with_blocks[page_num - 1]

    # 收集 node_1 的内容块（包含子章节）
    chapter_node = mock_doc_structure.all_nodes["node_1"]
    blocks_with_pages, page_nums = service._collect_chapter_blocks(
        reg_id="test_reg",
        chapter_node=chapter_node,
        doc_structure=mock_doc_structure,
        include_children=True,
    )

    # 验证结果
    assert len(blocks_with_pages) == 6, "应该收集到6个内容块（node_1: 2, node_2: 2, node_3: 2）"
    assert page_nums == {1, 2, 3}, "应该涉及第1、2、3页"

    # 验证不包含其他章节的内容
    for block, page_num in blocks_with_pages:
        assert block.chapter_node_id in ["node_1", "node_2", "node_3"]


def test_collect_descendant_node_ids(mock_doc_structure):
    """测试递归收集子孙节点ID"""
    service = ExportService()

    root_node = mock_doc_structure.all_nodes["node_1"]
    descendants = service._collect_descendant_node_ids(root_node, mock_doc_structure)

    assert descendants == {"node_2", "node_3"}, "应该收集到所有子节点ID"


def test_build_markdown_from_blocks():
    """测试从内容块构建 Markdown"""
    service = ExportService()

    blocks_with_pages = [
        (ContentBlock(
            block_id="test_reg_1_0",
            block_type="heading",
            order_in_page=0,
            content_markdown="## 2.1 第一章",
        ), 1),
        (ContentBlock(
            block_id="test_reg_1_1",
            block_type="text",
            order_in_page=1,
            content_markdown="这是第一章的内容。",
        ), 1),
        (ContentBlock(
            block_id="test_reg_2_0",
            block_type="table",
            order_in_page=0,
            content_markdown="| 列1 | 列2 |\n|-----|-----|\n| A   | B   |",
        ), 2),
    ]

    from regreader.storage.models import ExportMetadata
    metadata = ExportMetadata(
        reg_id="test_reg",
        title="测试规程",
        chapter="第一章",
        section_number="2.1",
        export_mode="chapter",
    )

    config = ExportConfig(
        include_yaml_frontmatter=False,
        include_page_markers=True,
    )

    content = service._build_markdown_from_blocks(blocks_with_pages, metadata, config)

    # 验证内容
    assert "# 测试规程" in content
    assert "## 第一章" in content
    assert "<!-- Page 1 -->" in content
    assert "<!-- Page 2 -->" in content
    assert "这是第一章的内容。" in content
    assert "| 列1 | 列2 |" in content


def test_calculate_stats_from_blocks():
    """测试从内容块计算统计信息"""
    service = ExportService()

    blocks_with_pages = [
        (ContentBlock(
            block_id="test_reg_1_0",
            block_type="text",
            order_in_page=0,
            content_markdown="文本内容",
        ), 1),
        (ContentBlock(
            block_id="test_reg_1_1",
            block_type="table",
            order_in_page=1,
            content_markdown="表格内容",
        ), 1),
        (ContentBlock(
            block_id="test_reg_2_0",
            block_type="table",
            order_in_page=0,
            content_markdown="另一个表格",
        ), 2),
    ]

    content = "测试内容"
    stats = service._calculate_stats_from_blocks(blocks_with_pages, content)

    assert stats["pages"] == 2, "应该涉及2个页面"
    assert stats["blocks"] == 3, "应该有3个内容块"
    assert stats["tables"] == 2, "应该有2个表格"
    assert "size_kb" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
