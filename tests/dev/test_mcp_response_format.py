"""Test MCP tool response format to debug parsing issue."""

from grid_code.index.hybrid_search import HybridSearch


def test_smart_search_response():
    """Test smart_search and print the actual response format."""
    print("=" * 60)
    print("Testing HybridSearch response format")
    print("=" * 60)

    search = HybridSearch()

    # Test smart_search
    query = "稳态过电压控制装置"
    reg_id = "angui_2024"

    print(f"\nQuery: {query}")
    print(f"reg_id: {reg_id}")

    try:
        results = search.search(query=query, reg_id=reg_id, limit=5)

        print(f"\n--- Response Info ---")
        print(f"Type: {type(results).__name__}")
        print(f"Length: {len(results)}")

        if results:
            print(f"\nFirst 2 items:")
            for i, item in enumerate(results[:2]):
                print(f"  [{i}] type={type(item).__name__}")
                if hasattr(item, '__dict__'):
                    print(f"      attrs={list(vars(item).keys())}")
                    if hasattr(item, 'page_num'):
                        print(f"      page_num={item.page_num}")
                elif isinstance(item, dict):
                    print(f"      keys={list(item.keys())}")

        print(f"\n--- Full repr (first 500 chars) ---")
        print(repr(results)[:500])

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)


if __name__ == "__main__":
    test_smart_search_response()
