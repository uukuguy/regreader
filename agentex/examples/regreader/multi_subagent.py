"""
RegReader 多子智能体用法示例

展示如何使用多个专业化子智能体进行复杂查询。
"""

import asyncio
from dataclasses import dataclass
from typing import Any

from agentex import AgentResponse, Tool, ToolResult
from agentex.frameworks import create_agent
from regreader_agent import RegReaderConfig


@dataclass
class SubagentInfo:
    """子智能体信息"""
    name: str
    description: str
    agent: Any


class SearchSubagent:
    """搜索子智能体：专门负责内容检索"""

    def __init__(self, reg_id: str):
        self.name = "search-subagent"
        self.agent = create_agent(
            framework="claude",
            system_prompt="""你是一个专业的搜索助手。
你的任务是：
1. 理解用户的查询意图
2. 使用工具搜索相关内容
3. 提取关键信息并返回搜索结果

请保持回答简洁，直接提供搜索结果。""",
        )
        self._reg_id = reg_id

    async def search(self, query: str) -> str:
        response = await self.agent.chat(f"请搜索以下内容：{query}")
        return response.content


class TableSubagent:
    """表格子智能体：专门负责表格内容处理"""

    def __init__(self, reg_id: str):
        self.name = "table-subagent"
        self.agent = create_agent(
            framework="pydantic",
            system_prompt="""你是一个表格处理专家。
你的任务是：
1. 查找相关的表格内容
2. 解释表格的含义和结构
3. 提供表格数据的清晰呈现

请以Markdown表格格式返回结果。""",
        )
        self._reg_id = reg_id

    async def find_tables(self, topic: str) -> str:
        response = await self.agent.chat(f"请查找关于'{topic}'的表格内容")
        return response.content


class ReferenceSubagent:
    """引用子智能体：专门负责交叉引用解析"""

    def __init__(self, reg_id: str):
        self.name = "reference-subagent"
        self.agent = create_agent(
            framework="langgraph",
            system_prompt="""你是一个引用解析专家。
你的任务是：
1. 解析文档中的交叉引用
2. 追踪引用的来源和目标
3. 提供完整的引用链路

请清晰标注引用的出处和页码。""",
        )
        self._reg_id = reg_id

    async def resolve_refs(self, content: str) -> str:
        response = await self.agent.chat(f"请解析以下内容中的交叉引用：\n\n{content}")
        return response.content


class RegReaderMultiSubagent:
    """RegReader 多子智能体系统

    协调搜索、表格、引用三个专业化子智能体。
    """

    def __init__(self, config: RegReaderConfig):
        self.config = config

        # 初始化子智能体
        self.subagents: dict[str, SubagentInfo] = {}

        self.subagents["search"] = SubagentInfo(
            name="search-subagent",
            description="内容搜索",
            agent=SearchSubagent(config.reg_id),
        )

        self.subagents["table"] = SubagentInfo(
            name="table-subagent",
            description="表格处理",
            agent=TableSubagent(config.reg_id),
        )

        self.subagents["reference"] = SubagentInfo(
            name="reference-subagent",
            description="引用解析",
            agent=ReferenceSubagent(config.reg_id),
        )

    async def search(self, query: str) -> dict[str, str]:
        """使用所有子智能体进行搜索"""
        results = {}

        print("\n" + "=" * 60)
        print("多子智能体搜索")
        print("=" * 60)

        # 搜索子智能体
        print("\n[1/3] 搜索子智能体处理中...")
        results["search"] = await self.subagents["search"].agent.search(query)
        print(f"搜索完成，结果长度: {len(results['search'])} 字符")

        # 表格子智能体
        print("\n[2/3] 表格子智能体处理中...")
        results["table"] = await self.subagents["table"].agent.find_tables(query)
        print(f"表格查找完成，结果长度: {len(results['table'])} 字符")

        # 引用子智能体
        print("\n[3/3] 引用子智能体处理中...")
        if results["search"]:
            results["reference"] = await self.subagents["reference"].agent.resolve_refs(
                results["search"][:500]
            )
        else:
            results["reference"] = "无内容可解析"
        print(f"引用解析完成，结果长度: {len(results['reference'])} 字符")

        return results

    async def aggregate_results(self, results: dict[str, str]) -> str:
        """聚合多子智能体的结果"""
        # 主智能体用于聚合结果
        aggregator = create_agent(
            framework="claude",
            system_prompt="""你是一个结果聚合专家。
你的任务是将多个子智能体的结果整合成一个完整的答案。
请确保：
1. 内容完整覆盖用户查询
2. 结构清晰，层次分明
3. 标注信息来源

以Markdown格式返回最终答案。""",
        )

        combined_input = f"""
用户查询结果汇总：

=== 搜索结果 ===
{results.get('search', '')}

=== 表格内容 ===
{results.get('table', '')}

=== 引用解析 ===
{results.get('reference', '')}

请整合以上内容，提供完整的答案。
"""

        response = await aggregator.chat(combined_input)
        await aggregator.close()

        return response.content

    async def query(self, query: str) -> str:
        """执行完整的多子智能体查询"""
        # 并行执行子智能体任务
        results = await self.search(query)

        # 聚合结果
        final_answer = await self.aggregate_results(results)

        return final_answer

    async def close_all(self):
        """关闭所有子智能体"""
        for info in self.subagents.values():
            await info.agent.agent.close()


async def main():
    """主函数示例"""
    # API key 和 model 从环境变量读取
    config = RegReaderConfig(reg_id="angui_2024")

    print("=" * 60)
    print("RegReader 多子智能体用法示例")
    print("=" * 60)

    # 创建多子智能体系统
    system = RegReaderMultiSubagent(config)

    try:
        # 示例查询
        query = "母线失压的处理流程和安全要求"

        print(f"\n查询: {query}")

        # 执行查询
        result = await system.query(query)

        print("\n" + "=" * 60)
        print("最终答案")
        print("=" * 60)
        print(result)

    finally:
        await system.close_all()

    print("\n" + "=" * 60)
    print("多子智能体用法示例完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
