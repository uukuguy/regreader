"""
RegReader 基础用法示例

展示如何使用基于 AgentEx 的 RegReaderAgent 进行基础检索。
"""

import asyncio
from regreader_agent import RegReaderConfig, RegReaderAgent


async def main():
    """基础用法示例"""
    # 配置（API key 和 model 从环境变量读取）
    config = RegReaderConfig(reg_id="angui_2024")

    print("=" * 60)
    print("RegReader 基础用法示例")
    print("=" * 60)

    # 创建 Agent（使用 Claude 框架）
    agent = RegReaderAgent(config, framework="claude")

    try:
        # === 示例1: 简单查询 ===
        print("\n--- 简单查询 ---\n")

        response = await agent.chat("总则部分的主要内容是什么？")
        print(f"Q: 总则部分的主要内容是什么？")
        print(f"A: {response.content}")

        # === 示例2: 条款查询 ===
        print("\n--- 条款查询 ---\n")

        response = await agent.chat("高压设备工作的安全要求有哪些？")
        print(f"Q: 高压设备工作的安全要求有哪些？")
        print(f"A: {response.content}")

        # === 示例3: 多轮对话 ===
        print("\n--- 多轮对话 ---\n")

        await agent.chat("记住这个术语：母线失压")
        response = await agent.chat("我刚才提到的术语是什么？")
        print(f"Q: 我刚才提到的术语是什么？")
        print(f"A: {response.content}")

    finally:
        await agent.close()

    print("\n" + "=" * 60)
    print("基础用法示例完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
