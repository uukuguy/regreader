"""LangGraph Agent 实现

使用 LangGraph 框架实现 GridCode Agent，通过 MCP 协议调用工具。
"""

import json
from typing import Annotated, Any, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph.message import add_messages
from loguru import logger

from grid_code.agents.base import AgentResponse, BaseGridCodeAgent
from grid_code.agents.prompts import SYSTEM_PROMPT
from grid_code.config import get_settings
from grid_code.mcp import GridCodeMCPClient


class AgentState(TypedDict):
    """Agent 状态"""
    messages: Annotated[list[BaseMessage], add_messages]
    tool_calls: list[dict]
    sources: list[str]


class LangGraphAgent(BaseGridCodeAgent):
    """基于 LangGraph 的 Agent 实现

    通过 MCP 协议连接 GridCode MCP Server，
    使用 LangGraph 构建多轮工具调用工作流。

    架构:
        LangGraphAgent
            └── MCP Client (stdio)
                    └── GridCode MCP Server
                            └── PageStore (页面数据)
    """

    def __init__(
        self,
        reg_id: str | None = None,
        model: str | None = None,
    ):
        """
        初始化 LangGraph Agent

        Args:
            reg_id: 默认规程标识
            model: 模型名称
        """
        super().__init__(reg_id)

        settings = get_settings()
        self._model_name = model or settings.default_model

        api_key = settings.anthropic_api_key
        if not api_key:
            raise ValueError("未配置 Anthropic API Key")

        # 创建 LLM（带系统提示）
        self.llm = ChatAnthropic(
            model=self._model_name,
            api_key=api_key,
            max_tokens=4096,
        )

        # MCP 客户端（延迟初始化）
        self._mcp_client: GridCodeMCPClient | None = None
        self._tools_schema: list[dict] | None = None

        # 消息历史
        self.messages: list[BaseMessage] = []

    @property
    def name(self) -> str:
        return "LangGraphAgent"

    @property
    def model(self) -> str:
        return self._model_name

    async def _ensure_mcp_connected(self) -> None:
        """确保 MCP 客户端已连接"""
        if self._mcp_client is None:
            self._mcp_client = GridCodeMCPClient()
            await self._mcp_client.connect()
            self._tools_schema = self._mcp_client.get_tools_for_langchain()
            logger.debug(f"MCP client connected, tools: {[t['name'] for t in self._tools_schema]}")

    async def _call_mcp_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """通过 MCP 调用工具"""
        if self._mcp_client is None:
            raise RuntimeError("MCP client not connected")

        # 如果有默认 reg_id，自动填充
        if self.reg_id and "reg_id" in arguments and not arguments.get("reg_id"):
            arguments["reg_id"] = self.reg_id

        return await self._mcp_client.call_tool(name, arguments)

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        base_prompt = SYSTEM_PROMPT
        if self.reg_id:
            return base_prompt + f"\n\n# 当前规程上下文\n默认规程标识: {self.reg_id}"
        return base_prompt

    async def chat(self, message: str) -> AgentResponse:
        """
        与 Agent 对话

        实现多轮工具调用循环：
        1. 发送用户消息给 LLM
        2. 如果 LLM 返回工具调用，执行工具并继续
        3. 直到 LLM 返回最终回答

        Args:
            message: 用户消息

        Returns:
            AgentResponse
        """
        # 确保 MCP 连接
        await self._ensure_mcp_connected()

        # 绑定工具到 LLM
        llm_with_tools = self.llm.bind_tools(self._tools_schema)

        # 构建初始消息
        messages: list[BaseMessage] = [
            SystemMessage(content=self._build_system_prompt()),
            *self.messages,  # 历史消息
            HumanMessage(content=message),
        ]

        tool_calls: list[dict] = []
        sources: list[str] = []

        # 多轮工具调用循环
        max_iterations = 20
        for _ in range(max_iterations):
            # 调用 LLM
            response: AIMessage = await llm_with_tools.ainvoke(messages)
            messages.append(response)

            # 检查是否有工具调用
            if not response.tool_calls:
                # 没有工具调用，返回最终回答
                break

            # 处理工具调用
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]

                logger.debug(f"Calling tool: {tool_name} with args: {tool_args}")

                # 通过 MCP 调用工具
                try:
                    result = await self._call_mcp_tool(tool_name, tool_args)
                except Exception as e:
                    logger.error(f"Tool call failed: {e}")
                    result = {"error": str(e)}

                # 记录工具调用
                tool_calls.append({
                    "name": tool_name,
                    "input": tool_args,
                    "output": result,
                })

                # 提取来源
                self._extract_sources(result, sources)

                # 添加工具结果消息
                messages.append(ToolMessage(
                    content=json.dumps(result, ensure_ascii=False),
                    tool_call_id=tool_id,
                ))

        # 提取最终回答
        final_content = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and not msg.tool_calls:
                final_content = msg.content
                break

        # 更新消息历史（保留用户消息和最终回答）
        self.messages.append(HumanMessage(content=message))
        self.messages.append(AIMessage(content=final_content))

        return AgentResponse(
            content=final_content,
            sources=list(set(sources)),
            tool_calls=tool_calls,
        )

    def _extract_sources(self, result: Any, sources: list[str]) -> None:
        """从工具结果中提取来源信息"""
        if isinstance(result, dict):
            if "source" in result:
                sources.append(result["source"])
            for value in result.values():
                self._extract_sources(value, sources)
        elif isinstance(result, list):
            for item in result:
                self._extract_sources(item, sources)

    async def reset(self):
        """重置对话历史"""
        self.messages = []

    async def close(self):
        """关闭 MCP 连接"""
        if self._mcp_client:
            await self._mcp_client.disconnect()
            self._mcp_client = None
            self._tools_schema = None

    async def __aenter__(self) -> "LangGraphAgent":
        """异步上下文管理器"""
        await self._ensure_mcp_connected()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器"""
        await self.close()
