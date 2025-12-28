"""Claude Agent SDK 实现

使用 Claude Agent SDK (Anthropic SDK) 实现 GridCode Agent。
"""

import json
from typing import Any

from anthropic import Anthropic
from loguru import logger

from grid_code.agents.base import AgentResponse, BaseGridCodeAgent
from grid_code.agents.prompts import SYSTEM_PROMPT
from grid_code.config import get_settings
from grid_code.mcp.tools import GridCodeTools


class ClaudeAgent(BaseGridCodeAgent):
    """基于 Claude Agent SDK 的 Agent 实现"""

    def __init__(
        self,
        reg_id: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
    ):
        """
        初始化 Claude Agent

        Args:
            reg_id: 默认规程标识
            model: Claude 模型名称
            api_key: Anthropic API Key
        """
        super().__init__(reg_id)

        settings = get_settings()
        self._model = model or settings.default_model
        self._api_key = api_key or settings.anthropic_api_key

        if not self._api_key:
            raise ValueError("未配置 Anthropic API Key")

        self.client = Anthropic(api_key=self._api_key)
        self.tools = GridCodeTools()
        self.messages: list[dict] = []

        # 定义工具 schema
        self._tool_definitions = self._build_tool_definitions()

    @property
    def name(self) -> str:
        return "ClaudeAgent"

    @property
    def model(self) -> str:
        return self._model

    def _build_tool_definitions(self) -> list[dict]:
        """构建 Claude 工具定义"""
        return [
            {
                "name": "get_toc",
                "description": "获取安规的章节目录树及页码范围。在开始搜索前，应先调用此工具了解规程的整体结构。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "reg_id": {
                            "type": "string",
                            "description": "规程标识，如 'angui_2024'",
                        }
                    },
                    "required": ["reg_id"],
                },
            },
            {
                "name": "smart_search",
                "description": "在安规中执行混合检索（关键词+语义）。返回最相关的内容片段。建议先通过 get_toc 确定章节范围。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索查询，如 '母线失压处理'",
                        },
                        "reg_id": {
                            "type": "string",
                            "description": "规程标识",
                        },
                        "chapter_scope": {
                            "type": "string",
                            "description": "限定章节范围（可选），如 '第六章'",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "返回结果数量限制，默认 10",
                            "default": 10,
                        },
                    },
                    "required": ["query", "reg_id"],
                },
            },
            {
                "name": "read_page_range",
                "description": "读取连续页面的完整 Markdown 内容。自动处理跨页表格拼接。单次最多读取 10 页。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "reg_id": {
                            "type": "string",
                            "description": "规程标识",
                        },
                        "start_page": {
                            "type": "integer",
                            "description": "起始页码",
                        },
                        "end_page": {
                            "type": "integer",
                            "description": "结束页码",
                        },
                    },
                    "required": ["reg_id", "start_page", "end_page"],
                },
            },
            {
                "name": "list_regulations",
                "description": "列出所有已入库的规程。",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
            },
        ]

    def _execute_tool(self, name: str, arguments: dict) -> Any:
        """执行工具调用"""
        logger.debug(f"执行工具: {name}, 参数: {arguments}")

        # 如果有默认 reg_id，自动填充
        if self.reg_id and "reg_id" in arguments and not arguments.get("reg_id"):
            arguments["reg_id"] = self.reg_id

        if name == "get_toc":
            return self.tools.get_toc(**arguments)
        elif name == "smart_search":
            return self.tools.smart_search(**arguments)
        elif name == "read_page_range":
            return self.tools.read_page_range(**arguments)
        elif name == "list_regulations":
            return self.tools.list_regulations()
        else:
            return {"error": f"未知工具: {name}"}

    async def chat(self, message: str) -> AgentResponse:
        """
        与 Agent 对话

        Args:
            message: 用户消息

        Returns:
            AgentResponse
        """
        # 添加用户消息
        self.messages.append({"role": "user", "content": message})

        tool_calls = []
        sources = []

        # 循环处理工具调用
        while True:
            response = self.client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=self._tool_definitions,
                messages=self.messages,
            )

            # 检查是否需要工具调用
            if response.stop_reason == "tool_use":
                # 处理工具调用
                assistant_content = response.content
                self.messages.append({"role": "assistant", "content": assistant_content})

                tool_results = []
                for block in assistant_content:
                    if block.type == "tool_use":
                        tool_name = block.name
                        tool_input = block.input
                        tool_id = block.id

                        # 执行工具
                        result = self._execute_tool(tool_name, tool_input)
                        tool_calls.append({
                            "name": tool_name,
                            "input": tool_input,
                            "output": result,
                        })

                        # 收集来源信息
                        if isinstance(result, dict) and "source" in result:
                            sources.append(result["source"])
                        elif isinstance(result, list):
                            for item in result:
                                if isinstance(item, dict) and "source" in item:
                                    sources.append(item["source"])

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "content": json.dumps(result, ensure_ascii=False),
                        })

                # 添加工具结果
                self.messages.append({"role": "user", "content": tool_results})

            else:
                # 生成最终回答
                final_content = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        final_content += block.text

                self.messages.append({"role": "assistant", "content": final_content})

                return AgentResponse(
                    content=final_content,
                    sources=list(set(sources)),  # 去重
                    tool_calls=tool_calls,
                )

    async def reset(self):
        """重置对话历史"""
        self.messages = []
