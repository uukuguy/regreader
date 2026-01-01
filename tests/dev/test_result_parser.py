"""Test result_parser with various tool_response formats."""

from grid_code.agents.result_parser import parse_tool_result, _unwrap_text_content


def test_parse_smart_search_list():
    """Test parsing a list of search results (direct MCP format)."""
    result = [
        {"content": "测试内容1", "page_num": 148, "score": 0.85},
        {"content": "测试内容2", "page_num": 149, "score": 0.80},
    ]
    summary = parse_tool_result("mcp__gridcode__smart_search", result)
    print(f"List format: result_count={summary.result_count}, pages={summary.page_sources}")
    assert summary.result_count == 2
    assert 148 in summary.page_sources


def test_parse_smart_search_dict():
    """Test parsing a dict with results key."""
    result = {
        "results": [
            {"content": "测试内容1", "page_num": 148, "score": 0.85},
            {"content": "测试内容2", "page_num": 149, "score": 0.80},
        ]
    }
    summary = parse_tool_result("mcp__gridcode__smart_search", result)
    print(f"Dict format: result_count={summary.result_count}, pages={summary.page_sources}")
    assert summary.result_count == 2


def test_parse_smart_search_json_string():
    """Test parsing a JSON string."""
    import json
    result = json.dumps([
        {"content": "测试内容1", "page_num": 148, "score": 0.85},
    ])
    summary = parse_tool_result("mcp__gridcode__smart_search", result)
    print(f"JSON string: result_count={summary.result_count}, pages={summary.page_sources}")
    assert summary.result_count == 1


def test_parse_smart_search_empty():
    """Test parsing empty results."""
    result = []
    summary = parse_tool_result("mcp__gridcode__smart_search", result)
    print(f"Empty list: result_count={summary.result_count}")
    assert summary.result_count == 0


def test_parse_smart_search_text_content():
    """Test parsing Claude SDK TextContent format (potential issue)."""
    # Claude SDK might wrap results in TextContent objects
    # This tests if the result is a string representation
    result = "[]"  # Empty JSON array as string
    summary = parse_tool_result("mcp__gridcode__smart_search", result)
    print(f"Empty JSON string: result_count={summary.result_count}")
    assert summary.result_count == 0


def test_parse_smart_search_nested_list():
    """Test parsing potentially nested format from MCP SSE."""
    # MCP SSE might wrap in list of TextContent
    result = [{"type": "text", "text": '[{"content": "test", "page_num": 148}]'}]
    summary = parse_tool_result("mcp__gridcode__smart_search", result)
    print(f"Nested TextContent: result_count={summary.result_count}, pages={summary.page_sources}")
    assert summary.result_count == 1
    assert 148 in summary.page_sources


def test_unwrap_text_content():
    """Test _unwrap_text_content function directly."""
    import json

    # Test single TextContent with JSON array
    result = [{"type": "text", "text": '[{"page_num": 148}, {"page_num": 149}]'}]
    unwrapped = _unwrap_text_content(result)
    print(f"Unwrap single TextContent: {unwrapped}")
    assert isinstance(unwrapped, list)
    assert len(unwrapped) == 2
    assert unwrapped[0]["page_num"] == 148

    # Test multiple TextContent items
    result = [
        {"type": "text", "text": '[{"page_num": 1}'},
        {"type": "text", "text": ', {"page_num": 2}]'},
    ]
    unwrapped = _unwrap_text_content(result)
    print(f"Unwrap multiple TextContent: {unwrapped}")
    assert isinstance(unwrapped, list)
    assert len(unwrapped) == 2

    # Test non-TextContent format (should return as-is)
    result = [{"page_num": 148}]
    unwrapped = _unwrap_text_content(result)
    assert unwrapped == result

    print("  ✓ _unwrap_text_content tests passed")


def test_realistic_mcp_response():
    """Test with realistic MCP SSE response format."""
    # This mimics what Claude Agent SDK might receive from MCP Server
    import json

    # Realistic search results from MCP
    mcp_results = [
        {
            "content": "稳态过电压控制装置在特高压南阳站的应用",
            "page_num": 148,
            "chapter_path": ["第六章", "6.2 过电压保护"],
            "score": 0.92,
            "source": "angui_2024:P148",
        },
        {
            "content": "误动作分析与处理措施",
            "page_num": 149,
            "chapter_path": ["第六章", "6.2 过电压保护"],
            "score": 0.88,
            "source": "angui_2024:P149",
        },
    ]

    # Format 1: Direct list (MCP direct mode)
    summary = parse_tool_result("smart_search", mcp_results)
    print(f"Direct list: {summary.result_count} results, pages={summary.page_sources}")
    assert summary.result_count == 2
    assert 148 in summary.page_sources

    # Format 2: Wrapped in TextContent (Claude SDK SSE mode)
    wrapped = [{"type": "text", "text": json.dumps(mcp_results)}]
    summary = parse_tool_result("smart_search", wrapped)
    print(f"TextContent wrapped: {summary.result_count} results, pages={summary.page_sources}")
    assert summary.result_count == 2
    assert 148 in summary.page_sources

    print("  ✓ Realistic MCP response tests passed")


if __name__ == "__main__":
    print("=" * 60)
    print("Testing result_parser with various formats")
    print("=" * 60)

    test_parse_smart_search_list()
    test_parse_smart_search_dict()
    test_parse_smart_search_json_string()
    test_parse_smart_search_empty()
    test_parse_smart_search_text_content()

    print("\n--- Testing TextContent format ---")
    test_parse_smart_search_nested_list()
    test_unwrap_text_content()

    print("\n--- Testing realistic MCP response ---")
    test_realistic_mcp_response()

    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)
