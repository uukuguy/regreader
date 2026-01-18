"""测试 Coordinator 多轮对话场景

验证：
1. 多轮查询的 session_state 持久化
2. accumulated_sources 去重逻辑
3. query_count 累加
"""

import asyncio
from pathlib import Path

from regreader.orchestration.coordinator import Coordinator


async def test_multi_turn_conversation():
    """测试多轮对话场景"""
    print("=" * 60)
    print("测试多轮对话场景")
    print("=" * 60)

    # 创建临时工作目录
    work_dir = Path("./test_multi_turn_output")
    work_dir.mkdir(exist_ok=True)

    # 初始化 Coordinator
    coordinator = Coordinator(work_dir=work_dir)
    print(f"\n✓ Coordinator 初始化")
    print(f"  - 会话ID: {coordinator.session_state.session_id}")

    # === 第一轮查询 ===
    print("\n" + "=" * 60)
    print("第一轮查询")
    print("=" * 60)

    await coordinator.log_query(
        query="母线失压如何处理？",
        hints={"chapter_scope": "第六章"},
        reg_id="angui_2024"
    )

    await coordinator.write_result(
        content="母线失压处理方法...",
        sources=["angui_2024:p14", "angui_2024:p15", "angui_2024:p16"],
        tool_calls=[{"tool": "smart_search"}]
    )

    print(f"✓ 第一轮完成")
    print(f"  - query_count: {coordinator.session_state.query_count}")
    print(f"  - accumulated_sources: {coordinator.session_state.accumulated_sources}")

    # === 第二轮查询（部分重复来源）===
    print("\n" + "=" * 60)
    print("第二轮查询（部分重复来源）")
    print("=" * 60)

    await coordinator.log_query(
        query="表6-2中注1的内容是什么？",
        hints={"table_hint": "表6-2", "annotation_hint": "注1"},
        reg_id="angui_2024"
    )

    await coordinator.write_result(
        content="表6-2注1内容...",
        sources=["angui_2024:p15", "angui_2024:p16", "angui_2024:p17"],  # p15, p16 重复
        tool_calls=[{"tool": "lookup_annotation"}]
    )

    print(f"✓ 第二轮完成")
    print(f"  - query_count: {coordinator.session_state.query_count}")
    print(f"  - accumulated_sources: {coordinator.session_state.accumulated_sources}")

    # === 第三轮查询（全新来源）===
    print("\n" + "=" * 60)
    print("第三轮查询（全新来源）")
    print("=" * 60)

    await coordinator.log_query(
        query="锦苏直流闭锁故障的处理流程？",
        hints={"chapter_scope": "第二章"},
        reg_id="angui_2024"
    )

    await coordinator.write_result(
        content="锦苏直流闭锁故障处理...",
        sources=["angui_2024:p123", "angui_2024:p124"],
        tool_calls=[{"tool": "smart_search"}]
    )

    print(f"✓ 第三轮完成")
    print(f"  - query_count: {coordinator.session_state.query_count}")
    print(f"  - accumulated_sources: {coordinator.session_state.accumulated_sources}")

    # === 验证结果 ===
    print("\n" + "=" * 60)
    print("验证结果")
    print("=" * 60)

    # 检查 query_count
    expected_count = 3
    actual_count = coordinator.session_state.query_count
    if actual_count == expected_count:
        print(f"✓ query_count 正确: {actual_count}")
    else:
        print(f"✗ query_count 错误: 期望 {expected_count}, 实际 {actual_count}")

    # 检查 accumulated_sources 去重
    expected_sources = [
        "angui_2024:p14", "angui_2024:p15", "angui_2024:p16",  # 第一轮
        "angui_2024:p17",  # 第二轮新增（p15, p16 已存在）
        "angui_2024:p123", "angui_2024:p124"  # 第三轮
    ]
    actual_sources = coordinator.session_state.accumulated_sources

    if actual_sources == expected_sources:
        print(f"✓ accumulated_sources 去重正确")
        print(f"  - 总来源数: {len(actual_sources)}")
    else:
        print(f"✗ accumulated_sources 去重错误")
        print(f"  - 期望: {expected_sources}")
        print(f"  - 实际: {actual_sources}")

    # 检查 session_state.json
    state_file = work_dir / "session_state.json"
    if state_file.exists():
        print(f"✓ session_state.json 已持久化")
    else:
        print(f"✗ session_state.json 未生成")

    # 检查 plan.md
    plan_file = work_dir / "plan.md"
    if plan_file.exists():
        content = plan_file.read_text()
        query_count_in_file = content.count("# Query")
        if query_count_in_file == 3:
            print(f"✓ plan.md 包含 3 轮查询记录")
        else:
            print(f"✗ plan.md 查询记录数错误: {query_count_in_file}")
    else:
        print(f"✗ plan.md 未生成")

    print("\n" + "=" * 60)
    print("✓ 多轮对话测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_multi_turn_conversation())
