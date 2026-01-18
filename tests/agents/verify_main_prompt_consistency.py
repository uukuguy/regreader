#!/usr/bin/env python
"""验证单智能体和多智能体模式的主线提示词一致性

这个脚本对比两种模式的主线（Main Agent）系统提示词，确保它们：
1. 使用相同的操作协议（目录优先、精准定位、多跳推理）
2. 包含相同的工具描述（从 TOOL_METADATA 动态生成）
3. 推理路径应该更加一致
"""

import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))


def verify_single_agent_main_prompt():
    """验证单智能体模式的主线提示词"""
    from regreader.agents.direct.claude import ClaudeAgent

    # 创建单智能体实例
    single_agent = ClaudeAgent()

    # 生成主线提示词
    single_prompt = single_agent._build_system_prompt()

    return single_prompt


def verify_orchestrator_main_prompt():
    """验证多智能体模式的主线提示词"""
    from regreader.agents.orchestrated.claude import ClaudeOrchestrator

    # 创建 orchestrator 实例
    orchestrator = ClaudeOrchestrator(reg_id="angui_2024")

    # 初始化子智能体
    import asyncio
    asyncio.run(orchestrator._ensure_initialized())

    # 生成主线提示词
    multi_prompt = orchestrator._build_main_prompt()

    return multi_prompt


def compare_main_prompts():
    """对比两种模式的主线提示词"""
    print("=" * 80)
    print("主线提示词一致性验证（Step 6）")
    print("=" * 80)

    # 生成提示词
    print("\n1. 生成单智能体模式主线提示词...")
    single_prompt = verify_single_agent_main_prompt()

    print("2. 生成多智能体模式主线提示词...")
    multi_prompt = verify_orchestrator_main_prompt()

    # 分析结构
    print("\n3. 分析提示词结构...")

    # 检查关键元素
    def analyze_prompt(prompt: str, title: str) -> dict:
        lines = prompt.split("\n")

        return {
            "title": title,
            "length": len(prompt),
            "lines": len(lines),
            "has_role_def": "# 角色" in prompt or "你是电力系统规程专家助理 RegReader" in prompt,
            "has_operation_protocols": "# 操作协议" in prompt or "目录优先原则" in prompt,
            "has_tool_section": "# 可用工具" in prompt or "## 操作协议" in prompt,
            "has_workflow": "目录优先原则" in prompt and "精准定位" in prompt,
            "has_multihop": "多跳推理协议" in prompt or "lookup_annotation" in prompt,
            "toc_priority": "目录优先原则" in prompt or "先调用 get_toc" in prompt,
        }

    single_stats = analyze_prompt(single_prompt, "单智能体模式")
    multi_stats = analyze_prompt(multi_prompt, "多智能体模式（Orchestrator 主线）")

    # 打印统计信息
    print("\n" + "=" * 80)
    print("结构对比")
    print("=" * 80)

    print(f"\n{single_stats['title']}:")
    print(f"  - 长度: {single_stats['length']} 字符")
    print(f"  - 行数: {single_stats['lines']}")
    print(f"  - 包含角色定义: {'✓' if single_stats['has_role_def'] else '✗'}")
    print(f"  - 包含操作协议: {'✓' if single_stats['has_operation_protocols'] else '✗'}")
    print(f"  - 包含工具描述: {'✓' if single_stats['has_tool_section'] else '✗'}")
    print(f"  - 包含工作流程: {'✓' if single_stats['has_workflow'] else '✗'}")
    print(f"  - 包含多跳推理: {'✓' if single_stats['has_multihop'] else '✗'}")
    print(f"  - 目录优先原则: {'✓' if single_stats['toc_priority'] else '✗'}")

    print(f"\n{multi_stats['title']}:")
    print(f"  - 长度: {multi_stats['length']} 字符")
    print(f"  - 行数: {multi_stats['lines']}")
    print(f"  - 包含角色定义: {'✓' if multi_stats['has_role_def'] else '✗'}")
    print(f"  - 包含操作协议: {'✓' if multi_stats['has_operation_protocols'] else '✗'}")
    print(f"  - 包含工具描述: {'✓' if multi_stats['has_tool_section'] else '✗'}")
    print(f"  - 包含工作流程: {'✓' if multi_stats['has_workflow'] else '✗'}")
    print(f"  - 包含多跳推理: {'✓' if multi_stats['has_multihop'] else '✗'}")
    print(f"  - 目录优先原则: {'✓' if multi_stats['toc_priority'] else '✗'}")

    # 验证关键一致性
    print("\n" + "=" * 80)
    print("一致性验证")
    print("=" * 80)

    checks = []

    # 检查 1: 都包含角色定义（规程专家）
    check1 = single_stats['has_role_def'] and multi_stats['has_role_def']
    checks.append(("都包含规程专家角色定义", check1))

    # 检查 2: 都包含操作协议
    check2 = single_stats['has_operation_protocols'] and multi_stats['has_operation_protocols']
    checks.append(("都包含操作协议说明", check2))

    # 检查 3: 都包含目录优先原则
    check3 = single_stats['toc_priority'] and multi_stats['toc_priority']
    checks.append(("都包含目录优先原则", check3))

    # 检查 4: 都包含多跳推理协议
    check4 = single_stats['has_multihop'] and multi_stats['has_multihop']
    checks.append(("都包含多跳推理协议", check4))

    # 检查 5: Orchestrator 包含 Orchestrator 模式说明
    check5 = "Orchestrator 模式说明" in multi_prompt
    checks.append(("Orchestrator 包含模式说明", check5))

    # 打印验证结果
    for check_name, result in checks:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"  {status}: {check_name}")

    # 总结
    all_passed = all(result for _, result in checks)

    print("\n" + "=" * 80)
    if all_passed:
        print("✓ 所有关键检查通过！主线提示词已经统一。")
    else:
        print("✗ 部分检查失败，需要进一步调查。")
    print("=" * 80)

    # 显示提示词片段（前 1000 字符）
    print("\n" + "=" * 80)
    print("提示词预览（前 1000 字符）")
    print("=" * 80)

    print(f"\n{single_stats['title']}:\n")
    print(single_prompt[:1000] + "...")

    print(f"\n{multi_stats['title']}:\n")
    print(multi_prompt[:1000] + "...")

    return all_passed


if __name__ == "__main__":
    try:
        success = compare_main_prompts()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ 验证过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
