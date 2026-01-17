"""SearchAgent: 文档搜索子智能体

负责文档搜索和内容提取的原子级任务执行。
支持主动识别任务，拆解为原子操作，调用 MCP 工具。
"""

import asyncio
from pathlib import Path
from typing import Any

from loguru import logger

# Claude Agent SDK imports
try:
    from claude_agent_sdk import (
        ClaudeAgentOptions,
        ClaudeSDKClient,
    )
    HAS_CLAUDE_SDK = True
except ImportError:
    HAS_CLAUDE_SDK = False
    ClaudeAgentOptions = None  # type: ignore
    ClaudeSDKClient = None  # type: ignore

from regreader.core.config import get_settings
from regreader.subagents.bash_fs_base import BaseSubagentFS, SubagentResult


class SearchAgent(BaseSubagentFS):
    """文档搜索子智能体

    职责：
    1. 接收主智能体的任务（如"从规程目录中定位关于母线失压的章节"）
    2. 主动拆解为原子操作（get_toc → smart_search → read_page_range）
    3. 调用 MCP 工具执行
    4. 记录过程到 steps.md
    5. 返回结果摘要

    支持的框架：claude, pydantic, langgraph
    """

    def __init__(
        self,
        workspace: Path,
        reg_id: str,
        framework: str = "claude",
        model: str | None = None,
        api_key: str | None = None,
        mcp_transport: str | None = None,
        mcp_host: str | None = None,
        mcp_port: int | None = None,
    ):
        """初始化 SearchAgent

        Args:
            workspace: 工作区路径
            reg_id: 规程 ID
            framework: 框架类型（claude/pydantic/langgraph）
            model: 模型名称（可选）
            api_key: API 密钥（可选）
            mcp_transport: MCP 传输方式（可选，从 CLI 传递）
            mcp_host: MCP 主机地址（可选，从 CLI 传递）
            mcp_port: MCP 端口（可选，从 CLI 传递）
        """
        super().__init__(
            workspace,
            reg_id,
            framework,
            mcp_transport=mcp_transport,
            mcp_host=mcp_host,
            mcp_port=mcp_port,
        )

        # 获取配置
        settings = get_settings()
        self.model = model or settings.llm_model_name
        self.api_key = api_key or settings.llm_api_key

        # MCP 客户端（用于调用工具）
        from regreader.mcp.client import RegReaderMCPClient

        # 使用传递的 MCP 配置或默认配置
        transport = self.mcp_transport or settings.mcp_transport
        server_url = f"http://{self.mcp_host}:{self.mcp_port}/sse"

        # 创建 MCP 客户端（但不立即连接）
        self.mcp_client = RegReaderMCPClient(
            transport=transport,
            server_url=server_url,
        )

        logger.info(
            f"SearchAgent 初始化: framework={framework}, reg_id={reg_id}, mcp_transport={transport}"
        )

    def decompose_task(self, task: str) -> list[dict[str, Any]]:
        """将任务拆解为原子操作

        这是核心能力：主动识别任务，决定如何拆解为原子操作。

        Args:
            task: 任务描述（从 task.md 读取）

        Returns:
            原子操作列表
        """
        logger.info(f"拆解任务: {task[:100]}...")

        # 暂时禁用 LLM 拆解，直接使用规则拆解（避免 asyncio 事件循环冲突）
        # TODO: 未来可以重新启用 LLM 拆解，但需要解决 sync/async 混用问题
        return self._rule_based_decomposition(task)

        # # 使用 LLM 拆解任务
        # # 这里使用 Claude SDK 的预设工具调用能力
        # if not HAS_CLAUDE_SDK:
        #     # 回退到规则拆解
        #     return self._rule_based_decomposition(task)
        #
        # # 使用 Claude SDK 拆解
        # return self._llm_based_decomposition(task)

    def _llm_based_decomposition(self, task: str) -> list[dict[str, Any]]:
        """使用 LLM 拆解任务

        Args:
            task: 任务描述

        Returns:
            原子操作列表
        """
        # 构建拆解提示词
        prompt = f"""你是任务拆解专家。请将以下任务拆解为原子操作。

可用工具：
1. get_toc(reg_id): 获取规程目录
2. smart_search(query, reg_id, chapter_scope): 智能搜索
3. read_page_range(reg_id, start_page, end_page): 读取页面范围
4. lookup_annotation(reg_id, annotation_id, page_hint): 查找注释

任务：
{task}

请返回原子操作序列，格式：
[
    {{"step": 1, "description": "...", "action": "get_toc", "params": {{"reg_id": "..."}}}},
    {{"step": 2, "description": "...", "action": "smart_search", "params": {{...}}}}
]

只返回 JSON，不要其他内容。
"""

        try:
            # 创建 Claude SDK Client
            options = ClaudeAgentOptions(
                system_prompt="你是任务拆解专家，只返回 JSON 格式的原子操作序列。",
                model=self.model,  # model 通过 options 传递
            )

            async def get_decomposition():
                result = ""
                async with ClaudeSDKClient(options=options) as client:
                    # 发送查询
                    await client.query(prompt, session_id="decomposition")

                    # 接收响应
                    async for event in client.receive_response():
                        if hasattr(event, "content"):
                            for block in event.content:
                                if hasattr(block, "text"):
                                    result += block.text
                return result

            # 检查是否已有运行中的事件循环
            try:
                loop = asyncio.get_running_loop()
                # 已有运行中的事件循环，使用 run_coroutine_threadsafe
                import concurrent.futures
                import threading

                if threading.current_thread() is threading.main_thread():
                    # 在主线程中，可以使用 run_coroutine_threadsafe
                    future = asyncio.run_coroutine_threadsafe(get_decomposition(), loop)
                    response = future.result(timeout=60)  # 60秒超时
                else:
                    # 在其他线程中，创建新的事件循环
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(asyncio.run, get_decomposition())
                        response = future.result()
            except RuntimeError:
                # 没有事件循环，创建新的
                response = asyncio.run(get_decomposition())

            # 解析 JSON
            import json  # noqa: F401

            # 提取 JSON（可能被包裹在 ```json 中）
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()

            steps = json.loads(response)
            logger.info(f"LLM 拆解完成，共 {len(steps)} 个原子操作")
            return steps

        except Exception as e:
            logger.warning(f"LLM 拆解失败，回退到规则拆解: {e}")
            return self._rule_based_decomposition(task)

    def _rule_based_decomposition(self, task: str) -> list[dict[str, Any]]:
        """基于规则拆解任务

        Args:
            task: 任务描述

        Returns:
            原子操作列表
        """
        steps = []
        step_num = 1

        # 规则 1: 如果任务涉及"定位章节"、"查找章节"，先 get_toc
        if any(keyword in task for keyword in ["定位", "章节", "目录", "找章节"]):
            steps.append(
                {
                    "step": step_num,
                    "description": "获取规程目录结构",
                    "action": "get_toc",
                    "params": {"reg_id": self.reg_id},
                }
            )
            step_num += 1

        # 规则 2: 如果任务涉及"搜索"、"查找"，使用 smart_search
        if any(keyword in task for keyword in ["搜索", "查找", "内容", "提取"]):
            # 尝试提取章节范围
            chapter_scope = None
            if "第" in task and "章" in task:
                # 简单提取：第六章、2.1.4 等
                import re

                chapter_match = re.search(r"(第.+?章|\d+\.\d+)", task)
                if chapter_match:
                    chapter_scope = chapter_match.group(1)

            # 提取搜索关键词
            query = task
            # 移除常见的任务描述词
            for word in ["从", "规程", "目录", "中", "定位", "获得", "提取", "相关", "内容"]:
                query = query.replace(word, "")

            steps.append(
                {
                    "step": step_num,
                    "description": f"搜索相关内容: {query}",
                    "action": "smart_search",
                    "params": {
                        "query": query.strip(),
                        "reg_id": self.reg_id,
                        "chapter_scope": chapter_scope,
                    },
                }
            )
            step_num += 1

        # 规则 3: 如果任务涉及"读取页面"、"获取内容"，使用 read_page_range
        if any(keyword in task for keyword in ["读取", "页面", "范围"]):
            # 默认读取 1-10 页（应该根据实际情况调整）
            steps.append(
                {
                    "step": step_num,
                    "description": "读取页面内容",
                    "action": "read_page_range",
                    "params": {
                        "reg_id": self.reg_id,
                        "start_page": 1,
                        "end_page": 10,
                    },
                }
            )

        # 如果没有匹配任何规则，默认使用 smart_search
        if not steps:
            steps.append(
                {
                    "step": 1,
                    "description": "智能搜索",
                    "action": "smart_search",
                    "params": {
                        "query": task,
                        "reg_id": self.reg_id,
                    },
                }
            )

        logger.info(f"规则拆解完成，共 {len(steps)} 个原子操作")
        return steps

    async def execute_atomic_step(self, step: dict[str, Any]) -> Any:
        """执行单个原子操作（异步）

        Args:
            step: 原子操作定义

        Returns:
            操作结果
        """
        action = step["action"]
        params = step["params"]

        logger.info(f"执行操作: {action} with params={params}")

        # 使用 MCP 客户端调用工具（异步方法）
        try:
            async with self.mcp_client:
                result = await self.mcp_client.call_tool(action, params)
                logger.info(f"操作成功: {action}")
                return result
        except Exception as e:
            logger.error(f"操作失败: {action}, error={e}")
            return {"error": str(e), "action": action, "params": params}

    def run(self) -> SubagentResult:
        """执行任务（主流程）

        Returns:
            SubagentResult: 执行结果
        """
        logger.info("SearchAgent 开始执行任务")

        result = super().run()

        logger.info(
            f"SearchAgent 任务完成: content_length={len(result.content)}, sources={len(result.sources)}"
        )

        return result
