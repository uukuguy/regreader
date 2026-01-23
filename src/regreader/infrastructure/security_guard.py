"""SecurityGuard 安全守卫

实现瑞士奶酪防御模型，提供目录隔离和权限控制。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from regreader.workspace import SessionWorkspace

# 可选依赖
try:
    import aiofiles
    HAS_AIOFILES = True
except ImportError:
    HAS_AIOFILES = False


class SecurityViolationError(Exception):
    """安全违规错误"""

    pass


class ToolAccessDeniedError(Exception):
    """工具访问被拒绝"""

    pass


@dataclass
class PermissionMatrix:
    """权限矩阵

    定义单个 Subagent 的访问权限。

    Attributes:
        subagent_name: Subagent 标识名
        readable_dirs: 可读目录列表
        writable_dirs: 可写目录列表
        allowed_tools: 允许使用的工具列表
        can_execute_scripts: 是否允许执行脚本
        max_file_size_mb: 最大文件大小限制（MB）
        allowed_extensions: 允许的文件扩展名
        denied_patterns: 禁止的路径模式
    """

    subagent_name: str
    """Subagent 标识名"""

    readable_dirs: list[Path] = field(default_factory=list)
    """可读目录列表"""

    writable_dirs: list[Path] = field(default_factory=list)
    """可写目录列表"""

    allowed_tools: list[str] = field(default_factory=list)
    """允许使用的工具列表（空列表表示允许所有）"""

    can_execute_scripts: bool = False
    """是否允许执行脚本"""

    max_file_size_mb: float = 10.0
    """最大文件大小限制（MB）"""

    allowed_extensions: list[str] = field(default_factory=list)
    """允许的文件扩展名（空列表表示允许所有）"""

    denied_patterns: list[str] = field(default_factory=list)
    """禁止的路径模式（正则表达式）"""

    def allows_tool(self, tool_name: str) -> bool:
        """检查是否允许使用指定工具

        Args:
            tool_name: 工具名称

        Returns:
            是否允许
        """
        if not self.allowed_tools:
            return True  # 空列表表示允许所有
        return tool_name in self.allowed_tools

    def to_dict(self) -> dict[str, Any]:
        """转换为字典

        Returns:
            权限矩阵字典
        """
        return {
            "subagent_name": self.subagent_name,
            "readable_dirs": [str(p) for p in self.readable_dirs],
            "writable_dirs": [str(p) for p in self.writable_dirs],
            "allowed_tools": self.allowed_tools,
            "can_execute_scripts": self.can_execute_scripts,
            "max_file_size_mb": self.max_file_size_mb,
            "allowed_extensions": self.allowed_extensions,
            "denied_patterns": self.denied_patterns,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PermissionMatrix:
        """从字典创建权限矩阵

        Args:
            data: 权限矩阵字典

        Returns:
            PermissionMatrix 实例
        """
        data = data.copy()
        data["readable_dirs"] = [Path(p) for p in data.get("readable_dirs", [])]
        data["writable_dirs"] = [Path(p) for p in data.get("writable_dirs", [])]
        return cls(**data)


# 预定义的权限配置
PREDEFINED_PERMISSIONS: dict[str, PermissionMatrix] = {
    "regsearch": PermissionMatrix(
        subagent_name="regsearch",
        readable_dirs=[
            Path("shared/"),
            Path("coordinator/plan.md"),
            Path("subagents/regsearch/"),
        ],
        writable_dirs=[
            Path("subagents/regsearch/scratch/"),
            Path("subagents/regsearch/logs/"),
        ],
        allowed_tools=[
            # BASE 工具
            "list_regulations",
            "get_toc",
            "smart_search",
            "read_page_range",
            # MULTI_HOP 工具
            "lookup_annotation",
            "search_tables",
            "resolve_reference",
            # CONTEXT 工具
            "search_annotations",
            "get_table_by_id",
            "get_block_with_context",
            # DISCOVERY 工具
            "find_similar_content",
            "compare_sections",
            # NAVIGATION 工具
            "get_tool_guide",
            "get_chapter_structure",
            "read_chapter_content",
        ],
        can_execute_scripts=False,
    ),
    "exec": PermissionMatrix(
        subagent_name="exec",
        readable_dirs=[
            Path("shared/"),
            Path("subagents/"),  # 可读取所有 subagent 的 scratch
        ],
        writable_dirs=[
            Path("subagents/exec/results/"),
            Path("subagents/exec/logs/"),
        ],
        allowed_tools=[],  # Exec 不使用 MCP 工具
        can_execute_scripts=True,
    ),
    "validator": PermissionMatrix(
        subagent_name="validator",
        readable_dirs=[
            Path("subagents/"),  # 可读取所有 subagent 的结果
        ],
        writable_dirs=[
            Path("subagents/validator/audit.log"),
        ],
        allowed_tools=[],  # Validator 不使用 MCP 工具
        can_execute_scripts=False,
    ),
}


@dataclass
class AuditEntry:
    """审计日志条目"""

    timestamp: datetime
    subagent: str
    action: str
    resource: str
    operation: str
    allowed: bool
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "subagent": self.subagent,
            "action": self.action,
            "resource": self.resource,
            "operation": self.operation,
            "allowed": self.allowed,
            "details": self.details,
        }

    def to_json(self) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False)


class SecurityGuard:
    """安全守卫

    实现瑞士奶酪防御模型：
    1. 目录隔离层 - 限制文件系统访问
    2. 工具控制层 - 限制 MCP 工具使用
    3. 审计日志层 - 记录所有访问尝试

    Attributes:
        session_workspace: 会话工作区（提供路径访问）
        audit_dir: 审计日志目录
        permissions: Subagent 权限映射
        strict_mode: 严格模式（违规时抛出异常）
    """

    def __init__(
        self,
        session_workspace: "SessionWorkspace | None" = None,
        strict_mode: bool = True,
    ):
        """初始化安全守卫

        Args:
            session_workspace: 会话工作区（提供路径访问）
            strict_mode: 严格模式
        """
        self.session_workspace = session_workspace
        self.strict_mode = strict_mode

        # Determine audit directory
        if session_workspace:
            self.audit_dir = session_workspace.logs_dir
        else:
            # Legacy path for backward compatibility
            self.audit_dir = Path.cwd() / "coordinator" / "logs"
            logger.warning(
                f"SecurityGuard initialized without session_workspace, "
                f"using legacy path: {self.audit_dir}"
            )

        # 复制预定义权限并解析为 session-aware 路径
        self.permissions: dict[str, PermissionMatrix] = {}
        for name, perm in PREDEFINED_PERMISSIONS.items():
            self.permissions[name] = self._resolve_session_paths(perm)

        # 确保审计目录存在
        self.audit_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_session_paths(self, perm: PermissionMatrix) -> PermissionMatrix:
        """将相对路径解析为 session-aware 绝对路径

        Args:
            perm: 权限矩阵

        Returns:
            解析后的权限矩阵
        """
        if not self.session_workspace:
            # Legacy mode: resolve relative to current directory
            project_root = Path.cwd()
            return PermissionMatrix(
                subagent_name=perm.subagent_name,
                readable_dirs=[
                    p if p.is_absolute() else project_root / p for p in perm.readable_dirs
                ],
                writable_dirs=[
                    p if p.is_absolute() else project_root / p for p in perm.writable_dirs
                ],
                allowed_tools=perm.allowed_tools.copy(),
                can_execute_scripts=perm.can_execute_scripts,
                max_file_size_mb=perm.max_file_size_mb,
                allowed_extensions=perm.allowed_extensions.copy(),
                denied_patterns=perm.denied_patterns.copy(),
            )

        # Session-aware mode: resolve paths relative to session workspace
        readable_dirs = []
        writable_dirs = []

        for p in perm.readable_dirs:
            if p.is_absolute():
                readable_dirs.append(p)
            else:
                # Map legacy paths to session workspace paths
                path_str = str(p)
                if path_str.startswith("shared/"):
                    # Global shared directory
                    readable_dirs.append(self.session_workspace.workspace_root / "shared" / path_str[7:])
                    # Also add session-specific shared
                    readable_dirs.append(self.session_workspace.shared_dir / path_str[7:])
                elif path_str.startswith("coordinator/"):
                    # Coordinator directory
                    readable_dirs.append(self.session_workspace.coordinator_dir / path_str[12:])
                elif path_str.startswith("subagents/"):
                    # Subagent directory
                    subagent_name = path_str.split("/")[1] if "/" in path_str[10:] else ""
                    if subagent_name:
                        rest_path = path_str[10 + len(subagent_name) + 1:] if len(path_str) > 10 + len(subagent_name) + 1 else ""
                        if rest_path:
                            readable_dirs.append(self.session_workspace.get_subagent_dir(subagent_name) / rest_path)
                        else:
                            readable_dirs.append(self.session_workspace.get_subagent_dir(subagent_name))
                    else:
                        # All subagents
                        readable_dirs.append(self.session_workspace.subagents_dir)
                else:
                    # Other relative paths
                    readable_dirs.append(self.session_workspace.session_dir / p)

        for p in perm.writable_dirs:
            if p.is_absolute():
                writable_dirs.append(p)
            else:
                # Map legacy paths to session workspace paths
                path_str = str(p)
                if path_str.startswith("subagents/"):
                    # Subagent directory
                    parts = path_str[10:].split("/", 1)
                    subagent_name = parts[0]
                    rest_path = parts[1] if len(parts) > 1 else ""
                    if rest_path:
                        writable_dirs.append(self.session_workspace.get_subagent_dir(subagent_name) / rest_path)
                    else:
                        writable_dirs.append(self.session_workspace.get_subagent_dir(subagent_name))
                else:
                    # Other relative paths
                    writable_dirs.append(self.session_workspace.session_dir / p)

        return PermissionMatrix(
            subagent_name=perm.subagent_name,
            readable_dirs=readable_dirs,
            writable_dirs=writable_dirs,
            allowed_tools=perm.allowed_tools.copy(),
            can_execute_scripts=perm.can_execute_scripts,
            max_file_size_mb=perm.max_file_size_mb,
            allowed_extensions=perm.allowed_extensions.copy(),
            denied_patterns=perm.denied_patterns.copy(),
        )

    def register_subagent(self, permission: PermissionMatrix) -> None:
        """注册 Subagent 权限

        Args:
            permission: 权限矩阵
        """
        self.permissions[permission.subagent_name] = self._resolve_session_paths(permission)
        logger.info(f"Registered security permissions for {permission.subagent_name}")

    def get_permission(self, subagent: str) -> PermissionMatrix | None:
        """获取 Subagent 权限

        Args:
            subagent: Subagent 名称

        Returns:
            权限矩阵，不存在返回 None
        """
        return self.permissions.get(subagent)

    def check_file_access(
        self,
        subagent: str,
        path: Path,
        operation: str,
    ) -> bool:
        """检查文件访问权限

        Args:
            subagent: Subagent 名称
            path: 目标路径
            operation: 操作类型（"read" 或 "write"）

        Returns:
            是否允许访问

        Raises:
            SecurityViolationError: 严格模式下访问被拒绝
        """
        perm = self.permissions.get(subagent)
        if not perm:
            allowed = False
            reason = f"Unknown subagent: {subagent}"
        else:
            # Resolve path: if relative, resolve against session workspace or cwd
            if path.is_absolute():
                abs_path = path
            else:
                if self.session_workspace:
                    abs_path = self.session_workspace.session_dir / path
                else:
                    abs_path = Path.cwd() / path

            if operation == "read":
                allowed_dirs = perm.readable_dirs
            elif operation == "write":
                allowed_dirs = perm.writable_dirs
            else:
                allowed = False
                reason = f"Unknown operation: {operation}"
                allowed_dirs = []

            allowed = any(self._is_under_path(abs_path, d) for d in allowed_dirs)
            reason = "" if allowed else f"Path {path} not in allowed {operation} directories"

        # 记录审计日志
        self.audit_log(
            action="file_access",
            subagent=subagent,
            details={
                "path": str(path),
                "operation": operation,
                "allowed": allowed,
                "reason": reason if not allowed else None,
            },
        )

        if not allowed and self.strict_mode:
            raise SecurityViolationError(f"File access denied for {subagent}: {reason}")

        return allowed

    def check_tool_access(self, subagent: str, tool_name: str) -> bool:
        """检查工具访问权限

        Args:
            subagent: Subagent 名称
            tool_name: 工具名称

        Returns:
            是否允许使用

        Raises:
            ToolAccessDeniedError: 严格模式下访问被拒绝
        """
        perm = self.permissions.get(subagent)
        if not perm:
            allowed = False
            reason = f"Unknown subagent: {subagent}"
        else:
            allowed = perm.allows_tool(tool_name)
            reason = "" if allowed else f"Tool {tool_name} not in allowed list"

        # 记录审计日志
        self.audit_log(
            action="tool_access",
            subagent=subagent,
            details={
                "tool_name": tool_name,
                "allowed": allowed,
                "reason": reason if not allowed else None,
            },
        )

        if not allowed and self.strict_mode:
            raise ToolAccessDeniedError(f"Tool access denied for {subagent}: {reason}")

        return allowed

    def check_script_execution(self, subagent: str, script_path: Path) -> bool:
        """检查脚本执行权限

        Args:
            subagent: Subagent 名称
            script_path: 脚本路径

        Returns:
            是否允许执行

        Raises:
            SecurityViolationError: 严格模式下执行被拒绝
        """
        perm = self.permissions.get(subagent)
        if not perm:
            allowed = False
            reason = f"Unknown subagent: {subagent}"
        elif not perm.can_execute_scripts:
            allowed = False
            reason = "Script execution not allowed"
        else:
            # 检查脚本是否在可读目录中
            # Resolve path: if relative, resolve against session workspace or cwd
            if script_path.is_absolute():
                abs_path = script_path
            else:
                if self.session_workspace:
                    abs_path = self.session_workspace.session_dir / script_path
                else:
                    abs_path = Path.cwd() / script_path

            allowed = any(self._is_under_path(abs_path, d) for d in perm.readable_dirs)
            reason = "" if allowed else f"Script {script_path} not in allowed directories"

        # 记录审计日志
        self.audit_log(
            action="script_execution",
            subagent=subagent,
            details={
                "script_path": str(script_path),
                "allowed": allowed,
                "reason": reason if not allowed else None,
            },
        )

        if not allowed and self.strict_mode:
            raise SecurityViolationError(f"Script execution denied for {subagent}: {reason}")

        return allowed

    def _is_under_path(self, target: Path, base: Path) -> bool:
        """检查目标路径是否在基础路径下

        Args:
            target: 目标路径
            base: 基础路径

        Returns:
            是否在基础路径下
        """
        try:
            target.resolve().relative_to(base.resolve())
            return True
        except ValueError:
            # 也检查是否是同一个文件
            return target.resolve() == base.resolve()

    def audit_log(
        self,
        action: str,
        subagent: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """记录审计日志

        Args:
            action: 操作类型
            subagent: Subagent 名称
            details: 详细信息
        """
        entry = AuditEntry(
            timestamp=datetime.now(),
            subagent=subagent,
            action=action,
            resource=details.get("path", details.get("tool_name", "")) if details else "",
            operation=details.get("operation", action) if details else action,
            allowed=details.get("allowed", True) if details else True,
            details=details or {},
        )

        # 写入审计日志
        log_file = self.audit_dir / "security_audit.jsonl"
        with log_file.open("a", encoding="utf-8") as f:
            f.write(entry.to_json() + "\n")

        # 根据结果记录日志
        if entry.allowed:
            logger.debug(f"[SecurityGuard] {action} allowed for {subagent}: {entry.resource}")
        else:
            logger.warning(f"[SecurityGuard] {action} DENIED for {subagent}: {entry.resource}")

    async def audit_log_async(
        self,
        action: str,
        subagent: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """异步记录审计日志

        Args:
            action: 操作类型
            subagent: Subagent 名称
            details: 详细信息
        """
        entry = AuditEntry(
            timestamp=datetime.now(),
            subagent=subagent,
            action=action,
            resource=details.get("path", details.get("tool_name", "")) if details else "",
            operation=details.get("operation", action) if details else action,
            allowed=details.get("allowed", True) if details else True,
            details=details or {},
        )

        log_file = self.audit_dir / "security_audit.jsonl"
        if HAS_AIOFILES:
            async with aiofiles.open(log_file, "a", encoding="utf-8") as f:
                await f.write(entry.to_json() + "\n")
        else:
            # 回退到同步写入
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(entry.to_json() + "\n")

    def get_audit_log(
        self,
        subagent: str | None = None,
        action: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """获取审计日志

        Args:
            subagent: 按 Subagent 过滤
            action: 按操作类型过滤
            since: 起始时间
            limit: 返回数量限制

        Returns:
            审计日志条目列表
        """
        entries = []
        log_file = self.audit_dir / "security_audit.jsonl"

        if not log_file.exists():
            return entries

        with log_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    entry = AuditEntry(
                        timestamp=datetime.fromisoformat(data["timestamp"]),
                        subagent=data["subagent"],
                        action=data["action"],
                        resource=data["resource"],
                        operation=data["operation"],
                        allowed=data["allowed"],
                        details=data.get("details", {}),
                    )

                    # 过滤
                    if subagent and entry.subagent != subagent:
                        continue
                    if action and entry.action != action:
                        continue
                    if since and entry.timestamp < since:
                        continue

                    entries.append(entry)

                    if len(entries) >= limit:
                        break
                except Exception as e:
                    logger.warning(f"Failed to parse audit entry: {e}")

        return entries

    def get_violations(
        self,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """获取安全违规记录

        Args:
            since: 起始时间
            limit: 返回数量限制

        Returns:
            违规记录列表
        """
        entries = []
        log_file = self.audit_dir / "security_audit.jsonl"

        if not log_file.exists():
            return entries

        with log_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    if data.get("allowed", True):
                        continue  # 跳过允许的操作

                    entry = AuditEntry(
                        timestamp=datetime.fromisoformat(data["timestamp"]),
                        subagent=data["subagent"],
                        action=data["action"],
                        resource=data["resource"],
                        operation=data["operation"],
                        allowed=False,
                        details=data.get("details", {}),
                    )

                    if since and entry.timestamp < since:
                        continue

                    entries.append(entry)

                    if len(entries) >= limit:
                        break
                except Exception as e:
                    logger.warning(f"Failed to parse audit entry: {e}")

        return entries

    def __repr__(self) -> str:
        return (
            f"SecurityGuard("
            f"subagents={list(self.permissions.keys())}, "
            f"strict_mode={self.strict_mode})"
        )
