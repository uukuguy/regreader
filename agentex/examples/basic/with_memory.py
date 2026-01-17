"""
记忆系统示例

展示 AgentEx 的记忆功能。
"""

import asyncio
from agentex.frameworks import create_agent
from agentex.shared import AgentMemory


async def main():
    """主函数"""
    # API key 和 model 从环境变量读取（ANTHROPIC_*）
    agent = create_agent(
        framework="claude",
        system_prompt="你是一个友好的助手，能够记住对话中的信息。",
    )

    try:
        # 第一轮对话
        print("=== 对话 1 ===")
        await agent.chat("我的名字是张三。")

        # 第二轮对话 - 测试记忆
        print("\n=== 对话 2 ===")
        response = await agent.chat("你知道我的名字吗？")
        print(f"Agent: {response.content}")

        # 第三轮对话
        print("\n=== 对话 3 ===")
        await agent.chat("我最喜欢的颜色是蓝色。")

        # 第四轮对话 - 测试记忆
        print("\n=== 对话 4 ===")
        response = await agent.chat("我刚才说我最喜欢什么颜色？")
        print(f"Agent: {response.content}")

        # 检查记忆内容
        print("\n=== 记忆内容 ===")
        if hasattr(agent, '_memory') and agent._memory:
            for item in agent._memory.get_history():
                print(f"- {item.role}: {item.content[:50]}...")

    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(main())
