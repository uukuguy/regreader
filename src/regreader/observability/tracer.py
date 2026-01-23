"""执行流程追踪和可视化

提供执行流程追踪功能，支持：
- 记录子任务执行流程
- 生成 Mermaid 流程图
- 显示耗时和状态
- 保存到 session 目录
"""

import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from regreader.observability.logging import get_trace_id


class NodeType(Enum):
    """节点类型"""

    QUERY = "query"  # 用户查询
    PLAN = "plan"  # 任务规划
    SUBTASK = "subtask"  # 子任务
    TOOL = "tool"  # 工具调用
    AGGREGATE = "aggregate"  # 结果聚合
    RESULT = "result"  # 最终结果


class NodeStatus(Enum):
    """节点状态"""

    PENDING = "pending"  # 待执行
    RUNNING = "running"  # 执行中
    SUCCESS = "success"  # 成功
    FAILED = "failed"  # 失败
    SKIPPED = "skipped"  # 跳过


@dataclass
class TraceNode:
    """追踪节点"""

    node_id: str
    node_type: NodeType
    name: str
    status: NodeStatus = NodeStatus.PENDING
    start_time: float | None = None
    end_time: float | None = None
    parent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float | None:
        """执行耗时（秒）"""
        if self.start_time is None or self.end_time is None:
            return None
        return self.end_time - self.start_time

    def start(self):
        """开始执行"""
        self.status = NodeStatus.RUNNING
        self.start_time = time.time()

    def complete(self, status: NodeStatus = NodeStatus.SUCCESS):
        """完成执行"""
        self.status = status
        self.end_time = time.time()



class ExecutionTracer:
    """执行流程追踪器

    特性:
    - 记录完整的执行流程
    - 生成 Mermaid 流程图
    - 支持并行执行可视化
    - 自动保存到 session 目录
    """

    def __init__(self, session_dir: Path | None = None):
        """初始化追踪器

        Args:
            session_dir: 会话目录（用于保存追踪文件）
        """
        self.session_dir = session_dir
        self.nodes: dict[str, TraceNode] = {}
        self.edges: list[tuple[str, str]] = []  # (from_id, to_id)
        self.trace_id = get_trace_id()
        self.start_time = time.time()

    def add_node(
        self,
        node_id: str,
        node_type: NodeType,
        name: str,
        parent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TraceNode:
        """添加追踪节点

        Args:
            node_id: 节点ID
            node_type: 节点类型
            name: 节点名称
            parent_id: 父节点ID
            metadata: 元数据

        Returns:
            创建的追踪节点
        """
        node = TraceNode(
            node_id=node_id,
            node_type=node_type,
            name=name,
            parent_id=parent_id,
            metadata=metadata or {},
        )
        self.nodes[node_id] = node

        # 添加边
        if parent_id:
            self.edges.append((parent_id, node_id))

        return node

    def start_node(self, node_id: str):
        """开始执行节点"""
        if node_id in self.nodes:
            self.nodes[node_id].start()

    def complete_node(self, node_id: str, status: NodeStatus = NodeStatus.SUCCESS):
        """完成节点执行"""
        if node_id in self.nodes:
            self.nodes[node_id].complete(status)

    def _get_node_style(self, node: TraceNode) -> str:
        """获取节点样式（Mermaid 格式）

        Args:
            node: 追踪节点

        Returns:
            Mermaid 样式字符串
        """
        # 根据状态选择颜色
        if node.status == NodeStatus.SUCCESS:
            color = "#90EE90"  # 浅绿色
        elif node.status == NodeStatus.FAILED:
            color = "#FFB6C1"  # 浅红色
        elif node.status == NodeStatus.RUNNING:
            color = "#87CEEB"  # 天蓝色
        elif node.status == NodeStatus.SKIPPED:
            color = "#D3D3D3"  # 浅灰色
        else:
            color = "#FFFFFF"  # 白色

        return f"style {node.node_id} fill:{color}"

    def _format_node_label(self, node: TraceNode) -> str:
        """格式化节点标签

        Args:
            node: 追踪节点

        Returns:
            格式化后的标签
        """
        label = node.name

        # 添加耗时信息
        if node.duration is not None:
            label += f"<br/>{node.duration:.2f}s"

        # 添加状态图标
        if node.status == NodeStatus.SUCCESS:
            label += " ✓"
        elif node.status == NodeStatus.FAILED:
            label += " ✗"

        return label

    def generate_mermaid(self) -> str:
        """生成 Mermaid 流程图

        Returns:
            Mermaid 格式的流程图代码
        """
        lines = ["```mermaid", "graph TD"]

        # 添加节点定义
        for node_id, node in self.nodes.items():
            label = self._format_node_label(node)
            
            # 根据节点类型选择形状
            if node.node_type == NodeType.QUERY:
                lines.append(f'    {node_id}["{label}"]')
            elif node.node_type == NodeType.RESULT:
                lines.append(f'    {node_id}["{label}"]')
            elif node.node_type == NodeType.SUBTASK:
                lines.append(f'    {node_id}("{label}")')
            elif node.node_type == NodeType.TOOL:
                lines.append(f'    {node_id}{{"{label}"}}')
            else:
                lines.append(f'    {node_id}["{label}"]')

        # 添加边
        for from_id, to_id in self.edges:
            lines.append(f"    {from_id} --> {to_id}")

        # 添加样式
        for node in self.nodes.values():
            lines.append(f"    {self._get_node_style(node)}")

        lines.append("```")
        return "\n".join(lines)

    def save_trace(self, filename: str = "trace.md"):
        """保存追踪结果到文件

        Args:
            filename: 文件名（默认 trace.md）
        """
        if self.session_dir is None:
            return

        trace_file = self.session_dir / filename
        trace_file.parent.mkdir(parents=True, exist_ok=True)

        with open(trace_file, "w", encoding="utf-8") as f:
            f.write(f"# 执行流程追踪\n\n")
            f.write(f"**Trace ID**: {self.trace_id}\n\n")
            f.write(f"**开始时间**: {datetime.fromtimestamp(self.start_time)}\n\n")
            
            # 写入 Mermaid 图
            f.write("## 执行流程图\n\n")
            f.write(self.generate_mermaid())
            f.write("\n\n")
            
            # 写入节点详情
            f.write("## 节点详情\n\n")
            for node_id, node in self.nodes.items():
                f.write(f"### {node.name} ({node_id})\n\n")
                f.write(f"- **类型**: {node.node_type.value}\n")
                f.write(f"- **状态**: {node.status.value}\n")
                if node.duration is not None:
                    f.write(f"- **耗时**: {node.duration:.2f}s\n")
                if node.metadata:
                    f.write(f"- **元数据**: {node.metadata}\n")
                f.write("\n")

    def get_statistics(self) -> dict[str, Any]:
        """获取执行统计信息

        Returns:
            统计信息字典
        """
        total_duration = time.time() - self.start_time
        
        stats = {
            "total_duration": total_duration,
            "node_count": len(self.nodes),
            "status_distribution": {},
            "type_distribution": {},
            "avg_duration_by_type": {},
        }

        # 统计状态分布
        for node in self.nodes.values():
            status = node.status.value
            stats["status_distribution"][status] = (
                stats["status_distribution"].get(status, 0) + 1
            )

        # 统计类型分布和平均耗时
        type_durations: dict[str, list[float]] = {}
        for node in self.nodes.values():
            node_type = node.node_type.value
            stats["type_distribution"][node_type] = (
                stats["type_distribution"].get(node_type, 0) + 1
            )
            
            if node.duration is not None:
                if node_type not in type_durations:
                    type_durations[node_type] = []
                type_durations[node_type].append(node.duration)

        # 计算平均耗时
        for node_type, durations in type_durations.items():
            stats["avg_duration_by_type"][node_type] = sum(durations) / len(durations)

        return stats



# 全局单例
_execution_tracer: ExecutionTracer | None = None


def get_tracer(session_dir: Path | None = None) -> ExecutionTracer:
    """获取全局 ExecutionTracer 实例

    Args:
        session_dir: 会话目录（首次调用时设置）

    Returns:
        全局 ExecutionTracer 单例
    """
    global _execution_tracer
    if _execution_tracer is None:
        _execution_tracer = ExecutionTracer(session_dir=session_dir)
    return _execution_tracer


def reset_tracer():
    """重置全局 ExecutionTracer（用于测试）"""
    global _execution_tracer
    _execution_tracer = None
