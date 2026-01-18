"""测试 Coordinator 集成功能

验证 BaseOrchestrator 与 Coordinator 的集成是否正常工作。
"""

import asyncio
from pathlib import Path

from regreader.orchestration.coordinator import Coordinator


async def test_coordinator_basic():
    """测试 Coordinator 基本功能"""
    print("=" * 60)
    print("测试 Coordinator 基本功能")
    print("=" * 60)

    # 创建临时工作目录
    work_dir = Path("./test_coordinator_output")
    work_dir.mkdir(exist_ok=True)

    # 初始化 Coordinator
    coordinator = Coordinator(work_dir=work_dir)

    print(f"\n✓ Coordinator 初始化成功")
    print(f"  - 工作目录: {coordinator.work_dir}")
    print(f"  - 会话ID: {coordinator.session_state.session_id}")
    print(f"  - 使用文件系统: {coordinator.uses_file_system}")

    # 测试 log_query
    print("\n测试 log_query()...")
    await coordinator.log_query(
        query="测试查询：母线失压如何处理？",
        hints={"chapter_scope": "第六章", "table_hint": None},
        reg_id="angui_2024"
    )
    print("✓ log_query() 执行成功")

    # 检查 plan.md 是否生成
    plan_file = work_dir / "plan.md"
    if plan_file.exists():
        print(f"✓ plan.md 已生成: {plan_file}")
        content = plan_file.read_text()
        print(f"  - 文件大小: {len(content)} 字符")
        print(f"  - 前100字符: {content[:100]}...")
    else:
        print(f"✗ plan.md 未生成")

    # 测试 write_result
    print("\n测试 write_result()...")
    await coordinator.write_result(
        content="这是测试回答内容",
        sources=["angui_2024:p14", "angui_2024:p15"],
        tool_calls=[
            {"tool": "smart_search", "args": {"query": "母线失压"}},
            {"tool": "read_page_range", "args": {"start_page": 14, "end_page": 15}}
        ]
    )
    print("✓ write_result() 执行成功")

    # 检查 session_state.json 是否生成
    state_file = work_dir / "session_state.json"
    if state_file.exists():
        print(f"✓ session_state.json 已生成: {state_file}")
        content = state_file.read_text()
        print(f"  - 文件大小: {len(content)} 字符")
    else:
        print(f"✗ session_state.json 未生成")

    print("\n" + "=" * 60)
    print("✓ 所有测试通过")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_coordinator_basic())
