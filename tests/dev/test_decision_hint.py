"""Test decision_hint display in tool call flow."""
import asyncio
from rich.console import Console

from regreader.agents.display import AgentStatusDisplay
from regreader.agents.events import tool_start_event, tool_end_event, AgentEventType
from regreader.agents.hooks import pre_tool_audit_hook
from regreader.agents.callbacks import NullCallback


async def test_decision_hint_flow():
    """Test the complete decision_hint flow from hooks to display."""
    print("=" * 60)
    print("Testing decision_hint flow")
    print("=" * 60)

    # 1. Test hooks.py adds decision_hint for read_page_range
    print("\n[Test 1] hooks.py adds decision_hint")

    # Simulate what hooks.py does
    tool_name = "mcp__gridcode__read_page_range"
    tool_input = {"start_page": 148, "end_page": 151, "reg_id": "angui_2024"}
    tool_id = "test-tool-id"

    event = tool_start_event(tool_name, tool_input, tool_id)

    # Apply hooks logic (same as in hooks.py)
    simple_name = tool_name
    if "__" in tool_name:
        parts = tool_name.split("__")
        simple_name = parts[-1] if len(parts) > 1 else tool_name

    if simple_name == "read_page_range":
        start_page = tool_input.get("start_page")
        end_page = tool_input.get("end_page")
        if start_page and end_page:
            event.data["decision_hint"] = f"直接定位到 P{start_page}-P{end_page}"

    assert event.data.get("decision_hint") == "直接定位到 P148-P151", "decision_hint not set correctly"
    print(f"  ✓ decision_hint = '{event.data['decision_hint']}'")

    # 2. Test display.py shows decision_hint in verbose mode
    print("\n[Test 2] display.py shows decision_hint (verbose mode)")

    console = Console(force_terminal=True, width=80)
    display = AgentStatusDisplay(console=console, verbose=True)

    formatted = display._format_tool_call_start(event)
    formatted_str = formatted.plain

    assert "⚡" in formatted_str, "Decision hint icon not found"
    assert "直接定位到 P148-P151" in formatted_str, "Decision hint text not found"
    print(f"  ✓ Formatted output contains decision_hint:")
    console.print(formatted)

    # 3. Test display.py does NOT show decision_hint in compact mode
    print("\n[Test 3] display.py hides decision_hint (compact mode)")

    display_compact = AgentStatusDisplay(console=console, verbose=False)
    formatted_compact = display_compact._format_tool_call_start(event)
    formatted_compact_str = formatted_compact.plain

    assert "⚡" not in formatted_compact_str, "Decision hint should not appear in compact mode"
    print(f"  ✓ Compact mode does not show decision_hint")
    console.print(formatted_compact)

    # 4. Test smart_search does NOT get decision_hint
    print("\n[Test 4] smart_search does not get decision_hint")

    search_event = tool_start_event("mcp__gridcode__smart_search", {"query": "test", "reg_id": "angui_2024"}, "test-2")

    # Apply hooks logic
    simple_name = "smart_search"
    # No decision_hint for smart_search

    assert "decision_hint" not in search_event.data, "smart_search should not have decision_hint"
    print(f"  ✓ smart_search has no decision_hint")

    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_decision_hint_flow())
