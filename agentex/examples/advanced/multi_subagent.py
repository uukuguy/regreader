"""
多子智能体示例

展示如何使用 AgentEx 创建和协调多个子智能体。
"""

import asyncio
from agentex.frameworks import create_agent, FrameworkType
from agentex.config import AgentConfig, LLMConfig


class ResearchSubagent:
    """研究子智能体：专门负责信息检索和总结"""

    def __init__(self):
        self.name = "research-agent"
        self.agent = create_agent(
            framework=FrameworkType.CLAUDE,
            config=AgentConfig(
                name="research-agent",
                llm=LLMConfig(),  # 使用环境变量 ANTHROPIC_*
                system_prompt="你是一个专业的研究助手。你的任务是搜索、收集和总结信息。",
            ),
        )

    async def research(self, topic: str) -> str:
        response = await self.agent.chat(f"请研究以下主题并提供详细总结：{topic}")
        return response.content

    async def close(self):
        await self.agent.close()


class WriterSubagent:
    """写作子智能体：专门负责内容创作"""

    def __init__(self):
        self.name = "writer-agent"
        self.agent = create_agent(
            framework=FrameworkType.PYDANTIC,
            config=AgentConfig(
                name="writer-agent",
                llm=LLMConfig(),  # 使用环境变量 OPENAI_*
                system_prompt="你是一个专业的写作助手。你的任务是根据提供的信息创作高质量内容。",
            ),
        )

    async def write(self, topic: str, research_data: str) -> str:
        response = await self.agent.chat(
            f"根据以下研究资料，撰写关于'{topic}的文章：\n\n{research_data}"
        )
        return response.content

    async def close(self):
        await self.agent.close()


class EditorSubagent:
    """编辑子智能体：专门负责内容审核和优化"""

    def __init__(self):
        self.name = "editor-agent"
        self.agent = create_agent(
            framework=FrameworkType.LANGGRAPH,
            config=AgentConfig(
                name="editor-agent",
                llm=LLMConfig(),  # 使用环境变量 OPENAI_*
                system_prompt="你是一个专业的编辑。你的任务是审核和优化文章内容，确保准确性和可读性。",
            ),
        )

    async def edit(self, article: str) -> str:
        response = await self.agent.chat(
            f"请审核以下文章，优化表达并纠正错误：\n\n{article}"
        )
        return response.content

    async def close(self):
        await self.agent.close()


class Orchestrator:
    """编排器：协调多个子智能体的工作流程"""

    def __init__(self):
        self.subagents: dict[str, ResearchSubagent | WriterSubagent | EditorSubagent] = {}

    def register(self, subagent):
        """注册子智能体"""
        self.subagents[subagent.name] = subagent

    async def execute_workflow(self, topic: str) -> dict[str, str]:
        """执行完整的工作流程"""
        results = {}

        # Step 1: 研究阶段
        print("=" * 50)
        print("Step 1: 研究阶段 - Research Agent")
        print("=" * 50)

        if "research-agent" in self.subagents:
            results["research"] = await self.subagents["research-agent"].research(topic)
            print(f"研究完成，结果长度: {len(results['research'])} 字符")
        else:
            results["research"] = f"关于 {topic} 的研究资料..."

        # Step 2: 写作阶段
        print("\n" + "=" * 50)
        print("Step 2: 写作阶段 - Writer Agent")
        print("=" * 50)

        if "writer-agent" in self.subagents:
            results["article"] = await self.subagents["writer-agent"].write(
                topic, results["research"]
            )
            print(f"写作完成，文章长度: {len(results['article'])} 字符")
        else:
            results["article"] = f"# {topic}\n\n基于研究撰写的文章内容..."

        # Step 3: 编辑阶段
        print("\n" + "=" * 50)
        print("Step 3: 编辑阶段 - Editor Agent")
        print("=" * 50)

        if "editor-agent" in self.subagents:
            results["final"] = await self.subagents["editor-agent"].edit(results["article"])
            print(f"编辑完成，最终长度: {len(results['final'])} 字符")
        else:
            results["final"] = results["article"]

        return results

    async def close_all(self):
        """关闭所有子智能体"""
        for subagent in self.subagents.values():
            await subagent.close()


async def main():
    """主函数"""
    # 创建编排器
    orchestrator = Orchestrator()

    # 注册子智能体
    orchestrator.register(ResearchSubagent())
    orchestrator.register(WriterSubagent())
    orchestrator.register(EditorSubagent())

    try:
        # 执行工作流程
        topic = "人工智能在医疗领域的应用"

        print("\n" + "#" * 60)
        print(f"# 开始执行工作流程：{topic}")
        print("#" * 60)

        results = await orchestrator.execute_workflow(topic)

        # 显示最终结果
        print("\n" + "=" * 50)
        print("最终文章")
        print("=" * 50)
        print(results["final"])

    finally:
        await orchestrator.close_all()


if __name__ == "__main__":
    asyncio.run(main())
