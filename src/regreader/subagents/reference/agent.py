"""ReferenceAgent: 引用子智能体

负责交叉引用解析的原子级任务执行。
"""

from pathlib import Path
from typing import Any

from loguru import logger
from regreader.subagents.bash_fs_base import BaseSubagentFS, SubagentResult


class ReferenceAgent(BaseSubagentFS):
    """引用子智能体

    职责：
    1. 接收主智能体的任务（如"解析交叉引用"）
    2. 主动拆解为原子操作（resolve_reference → lookup_annotation）
    3. 调用 MCP 工具执行
    4. 记录过程到 steps.md
    5. 返回结果摘要
    """

    def __init__(
        self,
        workspace: Path,
        reg_id: str,
        framework: str = "claude",
        mcp_transport: str | None = None,
        mcp_host: str | None = None,
        mcp_port: int | None = None,
    ):
        """初始化 ReferenceAgent

        Args:
            workspace: 工作区路径
            reg_id: 规程 ID
            framework: 框架类型
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
        from regreader.core.config import get_settings
        settings = get_settings()

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
            f"ReferenceAgent 初始化: framework={framework}, reg_id={reg_id}, mcp_transport={transport}"
        )

    def decompose_task(self, task: str) -> list[dict[str, Any]]:
        """将任务拆解为原子操作

        Args:
            task: 任务描述

        Returns:
            原子操作列表
        """
        steps = []

        # 规则 1: 如果任务涉及"引用"、"参见"、"见"
        if any(keyword in task for keyword in ["引用", "参见", "见", "交叉"]):
            # 提取引用文本
            import re

            # 查找类似"见第六章"的模式
            ref_match = re.search(r"见(.+?章)", task)
            if ref_match:
                reference_text = ref_match.group(0)
                steps.append(
                    {
                        "step": 1,
                        "description": f"解析引用: {reference_text}",
                        "action": "resolve_reference",
                        "params": {
                            "reg_id": self.reg_id,
                            "reference_text": reference_text,
                        },
                    }
                )

        # 如果没有匹配，默认使用 resolve_reference
        if not steps:
            steps.append(
                {
                    "step": 1,
                    "description": "解析引用",
                    "action": "resolve_reference",
                    "params": {
                        "reg_id": self.reg_id,
                        "reference_text": task,
                    },
                }
            )

        logger.info(f"ReferenceAgent 拆解完成，共 {len(steps)} 个原子操作")
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

        logger.info(f"ReferenceAgent 执行操作: {action} with params={params}")

        # 使用 MCP 客户端调用工具（异步方法）
        try:
            async with self.mcp_client:
                result = await self.mcp_client.call_tool(action, params)
                logger.info(f"ReferenceAgent 操作成功: {action}")
                return result
        except Exception as e:
            logger.error(f"ReferenceAgent 操作失败: {action}, error={e}")
            return {"error": str(e), "action": action, "params": params}
