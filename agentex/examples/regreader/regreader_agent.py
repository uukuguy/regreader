"""
RegReaderAgent 实现示例

展示如何基于 AgentEx 创建 RegReader 专用 Agent。
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from agentex import AgentResponse, Tool, ToolResult, AgentEvent
from agentex.frameworks import create_agent
from agentex.shared import StatusCallback


@dataclass
class RegReaderConfig:
    """RegReader 配置

    API key 和 model 从环境变量读取（ANTHROPIC_*）
    """
    reg_id: str
    api_key: str | None = None
    model: str | None = None
    base_url: str | None = None

    def __post_init__(self):
        # 从环境变量读取默认值
        import os
        self.api_key = self.api_key or os.getenv("ANTHROPIC_AUTH_TOKEN")
        self.model = self.model or os.getenv("ANTHROPIC_MODEL_NAME", "claude-sonnet-4-20250514")
        self.base_url = self.base_url or os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")


class RegReaderTool(Tool):
    """RegReader 工具

    提供规程检索功能。
    """

    def __init__(self, reg_id: str):
        self.reg_id = reg_id

    @property
    def name(self) -> str:
        return "search_regulations"

    @property
    def description(self) -> str:
        return f"在 {self.reg_id} 规程中搜索相关内容"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询",
                }
            },
            "required": ["query"]
        }

    async def _run(self, context: dict, query: str) -> str:
        """执行搜索"""
        # 这里只是示例，实际应该调用 MCP 工具
        return f"搜索结果: 在 {self.reg_id} 中找到与 '{query}' 相关的内容"


class RegReaderAgent:
    """RegReader Agent

    基于 AgentEx 构建的规程检索 Agent。
    这个类展示了如何使用 AgentEx 快速构建领域特定的 Agent。
    """

    def __init__(
        self,
        config: RegReaderConfig,
        framework: str = "claude",
        status_callback: StatusCallback | None = None,
    ):
        """初始化 RegReader Agent

        Args:
            config: RegReader 配置
            framework: 使用的框架 ("claude", "pydantic", "langgraph")
            status_callback: 状态回调
        """
        self.config = config
        self.framework = framework
        self.status_callback = status_callback

        # 创建 AgentEx 工具
        self.tool = RegReaderTool(config.reg_id)

        # 创建底层 Agent
        self._agent = create_agent(
            framework=framework,
            system_prompt=f"""你是一个专业的规程检索助手。
你的任务是帮助用户从 {config.reg_id} 规程中查找相关信息。
请用清晰、准确的方式回答用户的问题。""",
        )

    @property
    def name(self) -> str:
        """获取 Agent 名称"""
        return f"regreader-{self.config.reg_id}"

    @property
    def model(self) -> str:
        """获取使用的模型"""
        return self._agent.model

    async def chat(self, message: str) -> AgentResponse:
        """发送消息并获取响应"""
        response = await self._agent.chat(message)
        return response

    async def close(self):
        """释放资源"""
        await self._agent.close()


class MultiFrameworkAgent:
    """多框架 Agent 管理器

    同时管理多个框架的 Agent，方便比较不同框架的表现。
    """

    def __init__(self, config: RegReaderConfig):
        """初始化多框架 Agent

        Args:
            config: RegReader 配置
        """
        self.config = config
        self.agents: dict[str, RegReaderAgent] = {}

        # 创建三个框架的 Agent
        for framework in ["claude", "pydantic", "langgraph"]:
            self.agents[framework] = RegReaderAgent(config, framework)

    async def chat(self, message: str) -> dict[str, AgentResponse]:
        """同时向所有框架发送消息

        Args:
            message: 用户消息

        Returns:
            各框架的响应
        """
        responses = {}
        for framework, agent in self.agents.items():
            responses[framework] = await agent.chat(message)
        return responses

    async def close(self):
        """释放所有资源"""
        for agent in self.agents.values():
            await agent.close()


async def main():
    """主函数"""
    print("=" * 60)
    print("RegReader Agent 示例")
    print("=" * 60)

    # 创建配置（API key 和 model 从环境变量读取）
    config = RegReaderConfig(
        reg_id="test_regulation",
    )

    # === 示例1: 创建单框架 Agent ===
    print("\n--- 单框架 Agent ---\n")

    agent = RegReaderAgent(config, framework="claude")
    print(f"Agent 名称: {agent.name}")
    print(f"Agent 模型: {agent.model}")

    response = await agent.chat("你好，请介绍一下你自己。")
    print(f"Agent: {response.content}")

    # === 示例2: 创建多框架 Agent ===
    print("\n--- 多框架 Agent ---\n")

    multi_agent = MultiFrameworkAgent(config)
    print("创建了 3 个不同框架的 Agent")
    print("可以同时比较它们的响应")

    # 测试多框架响应
    responses = await multi_agent.chat("什么是母线失压？")
    for framework, response in responses.items():
        print(f"\n{framework}: {response.content[:100]}...")

    # === 清理 ===
    print("\n--- 清理 ---\n")
    await agent.close()
    await multi_agent.close()
    print("所有 Agent 已关闭")

    print("\n" + "=" * 60)
    print("RegReader Agent 示例完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
