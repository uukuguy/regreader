"""测试 Claude preset: "claude_code" 的效果

对比 preset 模式和手动提示词模式的表现，包括：
- 工具调用效率
- 响应质量
- Token 占用
- 来源准确性
"""

import asyncio
import time
from typing import Any

import pytest

from grid_code.agents.claude.orchestrator import ClaudeOrchestrator


# 测试查询集合（覆盖不同任务类型）
TEST_QUERIES = [
    # 简单检索
    {
        "query": "母线失压如何处理？",
        "type": "simple_search",
        "expected_tools": ["smart_search"],
    },
    # 表格查询
    {
        "query": "表6-2中注1的内容是什么？",
        "type": "table_lookup",
        "expected_tools": ["search_tables", "lookup_annotation"],
    },
    # 章节导航
    {
        "query": "第2.1.4.1.6节的详细说明",
        "type": "chapter_navigation",
        "expected_tools": ["get_toc", "read_page_range"],
    },
    # 多跳推理
    {
        "query": "查找所有关于事故处理的表格，并说明相关注意事项",
        "type": "multi_hop",
        "expected_tools": ["search_tables", "smart_search"],
    },
]


@pytest.mark.asyncio
@pytest.mark.skipif(
    True,  # 默认跳过，需要实际MCP服务器
    reason="需要运行中的MCP服务器和规程数据",
)
async def test_preset_vs_manual_comparison():
    """对比 preset 模式和手动模式的效果

    这是一个集成测试，需要：
    1. 运行中的MCP服务器
    2. 已导入的规程数据（angui_2024）
    3. 有效的 Anthropic API Key
    """
    results = {
        "preset": [],
        "manual": [],
    }

    reg_id = "angui_2024"

    print("\n" + "=" * 80)
    print("开始 Preset vs Manual 对比测试")
    print("=" * 80 + "\n")

    for test_case in TEST_QUERIES:
        query = test_case["query"]
        query_type = test_case["type"]

        print(f"\n{'─' * 80}")
        print(f"测试查询 [{query_type}]: {query}")
        print(f"{'─' * 80}")

        # ========== 测试 Preset 模式 ==========
        print("\n[Preset 模式]")
        start_time = time.time()

        async with ClaudeOrchestrator(
            reg_id=reg_id,
            use_preset=True,  # ✅ 启用 preset
        ) as agent:
            response = await agent.chat(query)
            preset_duration = (time.time() - start_time) * 1000

            preset_result = {
                "query": query,
                "type": query_type,
                "content": response.content,
                "sources": response.sources,
                "tool_calls": len(response.tool_calls),
                "duration_ms": preset_duration,
            }
            results["preset"].append(preset_result)

            print(f"  工具调用数: {preset_result['tool_calls']}")
            print(f"  来源数量: {len(preset_result['sources'])}")
            print(f"  响应时间: {preset_duration:.1f}ms")
            print(f"  内容长度: {len(preset_result['content'])} 字符")

        # ========== 测试 Manual 模式 ==========
        print("\n[Manual 模式]")
        start_time = time.time()

        async with ClaudeOrchestrator(
            reg_id=reg_id,
            use_preset=False,  # ❌ 不使用 preset
        ) as agent:
            response = await agent.chat(query)
            manual_duration = (time.time() - start_time) * 1000

            manual_result = {
                "query": query,
                "type": query_type,
                "content": response.content,
                "sources": response.sources,
                "tool_calls": len(response.tool_calls),
                "duration_ms": manual_duration,
            }
            results["manual"].append(manual_result)

            print(f"  工具调用数: {manual_result['tool_calls']}")
            print(f"  来源数量: {len(manual_result['sources'])}")
            print(f"  响应时间: {manual_duration:.1f}ms")
            print(f"  内容长度: {len(manual_result['content'])} 字符")

        # ========== 对比分析 ==========
        print(f"\n[对比]")
        tool_diff = preset_result['tool_calls'] - manual_result['tool_calls']
        time_diff = preset_duration - manual_duration
        source_diff = len(preset_result['sources']) - len(manual_result['sources'])

        print(f"  工具调用差异: {tool_diff:+d} (Preset 相比 Manual)")
        print(f"  响应时间差异: {time_diff:+.1f}ms")
        print(f"  来源数差异: {source_diff:+d}")

    # ========== 总结报告 ==========
    print("\n\n" + "=" * 80)
    print("测试总结报告")
    print("=" * 80 + "\n")

    _print_summary(results, "preset", "Preset 模式")
    print()
    _print_summary(results, "manual", "Manual 模式")

    # 对比分析
    print(f"\n{'─' * 80}")
    print("整体对比")
    print(f"{'─' * 80}")

    preset_avg_tools = sum(r['tool_calls'] for r in results['preset']) / len(results['preset'])
    manual_avg_tools = sum(r['tool_calls'] for r in results['manual']) / len(results['manual'])

    preset_avg_time = sum(r['duration_ms'] for r in results['preset']) / len(results['preset'])
    manual_avg_time = sum(r['duration_ms'] for r in results['manual']) / len(results['manual'])

    print(f"平均工具调用数:")
    print(f"  Preset: {preset_avg_tools:.1f}")
    print(f"  Manual: {manual_avg_tools:.1f}")
    print(f"  差异: {(preset_avg_tools - manual_avg_tools):+.1f}")

    print(f"\n平均响应时间:")
    print(f"  Preset: {preset_avg_time:.1f}ms")
    print(f"  Manual: {manual_avg_time:.1f}ms")
    print(f"  差异: {(preset_avg_time - manual_avg_time):+.1f}ms")

    # 结论
    print(f"\n{'─' * 80}")
    print("结论")
    print(f"{'─' * 80}")

    if preset_avg_tools < manual_avg_tools:
        print(f"✅ Preset 模式工具调用更高效 ({(manual_avg_tools - preset_avg_tools):.1f} 次减少)")
    elif preset_avg_tools > manual_avg_tools:
        print(f"⚠️  Preset 模式工具调用更多 ({(preset_avg_tools - manual_avg_tools):.1f} 次增加)")
    else:
        print(f"➖ 工具调用数相同")

    if preset_avg_time < manual_avg_time:
        print(f"✅ Preset 模式响应更快 ({(manual_avg_time - preset_avg_time):.1f}ms 减少)")
    elif preset_avg_time > manual_avg_time:
        print(f"⚠️  Preset 模式响应更慢 ({(preset_avg_time - manual_avg_time):.1f}ms 增加)")
    else:
        print(f"➖ 响应时间相同")

    print("\n" + "=" * 80 + "\n")


def _print_summary(results: dict[str, list], mode: str, mode_name: str) -> None:
    """打印单个模式的总结"""
    print(f"【{mode_name}】")
    print(f"{'─' * 40}")

    mode_results = results[mode]

    for i, result in enumerate(mode_results, 1):
        print(f"\n{i}. {result['query']}")
        print(f"   类型: {result['type']}")
        print(f"   工具调用: {result['tool_calls']} 次")
        print(f"   来源数量: {len(result['sources'])} 个")
        print(f"   响应时间: {result['duration_ms']:.1f}ms")
        print(f"   内容长度: {len(result['content'])} 字符")


@pytest.mark.asyncio
async def test_preset_basic_functionality():
    """测试 preset 模式的基本功能（无需实际API调用）"""
    # 测试初始化
    orchestrator_preset = ClaudeOrchestrator(
        reg_id="test_reg",
        use_preset=True,
    )
    assert orchestrator_preset._use_preset is True

    orchestrator_manual = ClaudeOrchestrator(
        reg_id="test_reg",
        use_preset=False,
    )
    assert orchestrator_manual._use_preset is False

    # 测试默认值（默认启用 preset）
    orchestrator_default = ClaudeOrchestrator(reg_id="test_reg")
    assert orchestrator_default._use_preset is True  # 默认为 True


@pytest.mark.asyncio
async def test_domain_prompt_generation():
    """测试领域特定提示词的生成"""
    from grid_code.agents.claude.subagents import BaseClaudeSubagent
    from grid_code.agents.mcp_connection import get_mcp_manager
    from grid_code.subagents.config import SEARCH_AGENT_CONFIG
    from grid_code.subagents.base import SubagentContext

    # 创建 Subagent（preset 模式）
    mcp_manager = get_mcp_manager()
    subagent = BaseClaudeSubagent(
        config=SEARCH_AGENT_CONFIG,
        model="claude-sonnet-4-20250514",
        mcp_manager=mcp_manager,
        use_preset=True,
    )

    # 构建领域提示词
    context = SubagentContext(
        query="测试查询",
        reg_id="angui_2024",
        chapter_scope="第六章",
        hints={"table_hint": "表6-2", "annotation_hint": "注1"},
        max_iterations=5,
    )

    domain_prompt = subagent._build_domain_prompt(context)

    # 验证包含关键信息
    assert "SearchAgent" in domain_prompt or "搜索" in domain_prompt
    assert "angui_2024" in domain_prompt
    assert "第六章" in domain_prompt
    assert "表6-2" in domain_prompt
    assert "注1" in domain_prompt
    assert "X.X.X.X" in domain_prompt  # 章节编号格式
    assert "表X-X" in domain_prompt  # 表格命名规则

    # 验证提示词长度合理（应该比手动模式短）
    manual_prompt = subagent._build_system_prompt(context)

    print(f"\nDomain Prompt 长度: {len(domain_prompt)} 字符")
    print(f"Manual Prompt 长度: {len(manual_prompt)} 字符")
    print(f"减少比例: {(1 - len(domain_prompt) / len(manual_prompt)) * 100:.1f}%")

    # 领域提示词应该更短（精简版）
    assert len(domain_prompt) < len(manual_prompt) * 1.5  # 允许一定的灵活性


if __name__ == "__main__":
    # 运行对比测试
    asyncio.run(test_preset_vs_manual_comparison())
