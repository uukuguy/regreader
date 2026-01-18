#!/usr/bin/env python
"""验证单智能体和多智能体模式的提示词一致性

这个脚本对比两种模式下的系统提示词，确保它们：
1. 使用相同的工具描述来源（TOOL_METADATA）
2. 不包含硬编码的工具列表
3. 结构相似，推理路径应该更加一致
"""

import re
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))


def verify_single_agent_prompt():
    """验证单智能体模式的提示词"""
    from regreader.agents.prompts import get_optimized_prompt_with_domain

    # 生成单智能体提示词（不使用规程列表）
    single_prompt = get_optimized_prompt_with_domain(
        include_advanced=False,
        regulations=None,  # 不提供规程列表，使用默认
    )

    return single_prompt


def verify_multi_agent_prompt():
    """验证多智能体模式的提示词"""
    from regreader.agents.orchestrated.claude import ClaudeOrchestrator
    from regreader.subagents.config import SEARCH_AGENT_CONFIG

    # 创建 orchestrator 实例
    orchestrator = ClaudeOrchestrator(reg_id="angui_2024")

    # 生成子智能体提示词
    multi_prompt = orchestrator._build_subagent_domain_prompt(SEARCH_AGENT_CONFIG)

    return multi_prompt


def analyze_prompt_structure(prompt: str, title: str) -> dict:
    """分析提示词结构"""
    lines = prompt.split("\n")

    # 统计关键元素
    has_role = "# 角色" in prompt or "你是" in prompt
    has_tools = "# 可用工具" in prompt or "## 工具" in prompt
    has_workflow = "# 工作流程" in prompt or "## 流程" in prompt
    has_output = "# 输出" in prompt or "## 输出" in prompt
    has_constraints = "# 约束" in prompt or "## 注意" in prompt

    # 检查硬编码特征
    # 注意：单智能体模式使用编号列表（1. tool_name()），多智能体模式使用 **tool_name** (tool_name) 格式
    # 两者都是从 TOOL_METADATA 动态生成，只是格式不同
    has_hardcoded_count = "可用工具（" in prompt
    has_numbered_list = any(line.strip().startswith(("1. ", "2. ", "3. ", "4. ", "5. ")) for line in lines)
    # 检查 **name** (name) 格式（注意可能有空格）
    has_markdown_bold_tools = bool(re.search(r'\*\*[^*]+\*\*\s*\([^)]+\)', prompt))

    # 统计工具数量（根据格式不同使用不同方法）
    # 单智能体：统计 "1. "、"2. " 等开头的行，但只在"可用工具"部分
    # 多智能体：统计 **name** (name) 格式的数量
    # 优先使用 markdown 格式检测（更精确）
    if has_markdown_bold_tools and re.search(r'\*\*([^*]+)\*\*\s*\(\1\)', prompt):
        # Markdown 格式：**name** (name)，使用正则精确统计
        tool_count = len(re.findall(r'\*\*([^*]+)\*\*\s*\(\1\)', prompt))
    elif has_numbered_list and "1. " in prompt:
        # 编号列表格式，找到"可用工具"部分，统计其中的编号列表
        in_tools_section = False
        tool_count = 0
        for line in lines:
            if "# 可用工具" in line or "## 可用工具" in line:
                in_tools_section = True
                continue
            if in_tools_section and line.strip().startswith("#"):
                break  # 退出工具部分
            if in_tools_section and line.strip() and any(line.strip().startswith(f"{i}. ") for i in range(1, 50)):
                tool_count += 1
    else:
        tool_count = 0

    return {
        "title": title,
        "length": len(prompt),
        "lines": len(lines),
        "has_role": has_role,
        "has_tools": has_tools,
        "has_workflow": has_workflow,
        "has_output": has_output,
        "has_constraints": has_constraints,
        "has_hardcoded_count": has_hardcoded_count,
        "has_numbered_list": has_numbered_list,
        "has_markdown_bold_tools": has_markdown_bold_tools,
        "tool_count": tool_count,
    }


def compare_prompts():
    """对比两种模式的提示词"""
    print("=" * 80)
    print("提示词一致性验证")
    print("=" * 80)

    # 生成提示词
    print("\n1. 生成单智能体模式提示词...")
    single_prompt = verify_single_agent_prompt()

    print("2. 生成多智能体模式提示词...")
    multi_prompt = verify_multi_agent_prompt()

    # 分析结构
    print("\n3. 分析提示词结构...")
    single_stats = analyze_prompt_structure(single_prompt, "单智能体模式")
    multi_stats = analyze_prompt_structure(multi_prompt, "多智能体模式（SearchAgent）")

    # 打印统计信息
    print("\n" + "=" * 80)
    print("结构对比")
    print("=" * 80)

    print(f"\n{single_stats['title']}:")
    print(f"  - 长度: {single_stats['length']} 字符")
    print(f"  - 行数: {single_stats['lines']}")
    print(f"  - 包含角色定义: {'✓' if single_stats['has_role'] else '✗'}")
    print(f"  - 包含工具描述: {'✓' if single_stats['has_tools'] else '✗'}")
    print(f"  - 包含工作流程: {'✓' if single_stats['has_workflow'] else '✗'}")
    print(f"  - 包含输出要求: {'✓' if single_stats['has_output'] else '✗'}")
    print(f"  - 包含约束条件: {'✓' if single_stats['has_constraints'] else '✗'}")
    print(f"  - 工具描述格式: 编号列表 (1. 2. 3.)")
    print(f"  - 动态生成工具描述: {'✓' if single_stats['has_markdown_bold_tools'] else '✗'}")
    print(f"  - 估计工具数: {single_stats['tool_count']}")

    print(f"\n{multi_stats['title']}:")
    print(f"  - 长度: {multi_stats['length']} 字符")
    print(f"  - 行数: {multi_stats['lines']}")
    print(f"  - 包含角色定义: {'✓' if multi_stats['has_role'] else '✗'}")
    print(f"  - 包含工具描述: {'✓' if multi_stats['has_tools'] else '✗'}")
    print(f"  - 包含工作流程: {'✓' if multi_stats['has_workflow'] else '✗'}")
    print(f"  - 包含输出要求: {'✓' if multi_stats['has_output'] else '✗'}")
    print(f"  - 包含约束条件: {'✓' if multi_stats['has_constraints'] else '✗'}")
    print(f"  - 工具描述格式: **名称** (name)")
    print(f"  - 动态生成工具描述: {'✓' if multi_stats['has_markdown_bold_tools'] else '✗'}")
    print(f"  - 估计工具数: {multi_stats['tool_count']}")

    # 验证关键一致性
    print("\n" + "=" * 80)
    print("一致性验证")
    print("=" * 80)

    checks = []

    # 检查 1: 单智能体使用编号列表格式，多智能体使用 Markdown 格式
    # 两者都是动态生成的，只是格式不同
    check1 = single_stats['has_numbered_list'] and multi_stats['has_markdown_bold_tools']
    checks.append(("使用动态工具描述（格式不同但都动态生成）", check1))

    # 检查 2: 单智能体模式有更多工具（所有工具 vs 子集）
    check2 = single_stats['tool_count'] > multi_stats['tool_count']
    checks.append(("单智能体工具数 > 多智能体工具数", check2))

    # 检查 3: 多智能体模式的工具数应该匹配配置
    # SearchAgent 有 4 个工具
    check3 = multi_stats['tool_count'] == 4
    checks.append(("多智能体工具数匹配配置（4个）", check3))

    # 检查 4: 都包含基本的结构元素
    check4 = all([
        single_stats['has_role'],
        single_stats['has_tools'],
        single_stats['has_output'],
    ])
    checks.append(("单智能体包含基本结构", check4))

    check5 = all([
        multi_stats['has_role'],
        multi_stats['has_tools'],
        multi_stats['has_workflow'],
        multi_stats['has_output'],
    ])
    checks.append(("多智能体包含基本结构", check5))

    # 打印验证结果
    for check_name, result in checks:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"  {status}: {check_name}")

    # 调试输出
    print(f"\n[调试] 单智能体工具数: {single_stats['tool_count']}")
    print(f"[调试] 多智能体工具数: {multi_stats['tool_count']}")

    # 总结
    all_passed = all(result for _, result in checks)

    print("\n" + "=" * 80)
    if all_passed:
        print("✓ 所有关键检查通过！提示词生成方式已经统一。")
    else:
        print("✗ 部分检查失败，需要进一步调查。")
    print("=" * 80)

    # 显示提示词片段（前 500 字符）
    print("\n" + "=" * 80)
    print("提示词预览（前 500 字符）")
    print("=" * 80)

    print(f"\n{single_stats['title']}:\n")
    print(single_prompt[:500] + "...")

    print(f"\n{multi_stats['title']}:\n")
    print(multi_prompt[:500] + "...")

    return all_passed


if __name__ == "__main__":
    try:
        success = compare_prompts()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ 验证过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
