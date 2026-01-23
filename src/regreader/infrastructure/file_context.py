"""FileContext 文件上下文管理器

实现 Bash+FS 范式的文件读写隔离，为 Subagent 提供受控的文件系统访问。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from regreader.workspace.session import SessionWorkspace

# 可选依赖
try:
    import aiofiles
    HAS_AIOFILES = True
except ImportError:
    HAS_AIOFILES = False


class FileAccessError(Exception):
    """文件访问权限错误"""

    pass


class FileNotFoundInContextError(Exception):
    """文件在上下文中不存在"""

    pass


@dataclass
class FileContext:
    """文件上下文管理器

    为 Subagent 提供受控的文件系统访问，实现读写隔离。

    核心职责：
    1. 管理 Subagent 的工作目录（scratch/, logs/）
    2. 提供 SKILL.md 读取
    3. 支持共享资源的只读访问
    4. 记录操作日志

    Attributes:
        subagent_name: Subagent 标识名
        session_workspace: 会话工作区（提供路径访问）
        can_read: 可读路径白名单
        can_write: 可写路径白名单
        base_dir: Subagent 工作目录根路径（从 session_workspace 派生）
    """

    subagent_name: str
    """Subagent 标识名"""

    session_workspace: SessionWorkspace | None = None
    """会话工作区（提供路径访问）"""

    can_read: list[Path] = field(default_factory=list)
    """可读路径白名单"""

    can_write: list[Path] = field(default_factory=list)
    """可写路径白名单"""

    base_dir: Path | None = field(default=None, init=False)
    """Subagent 工作目录根路径（从 session_workspace 派生）"""

    def __post_init__(self) -> None:
        """初始化后处理"""
        # 从 session_workspace 派生 base_dir
        if self.session_workspace:
            self.base_dir = self.session_workspace.get_subagent_dir(self.subagent_name)
        else:
            # 向后兼容：如果没有 session_workspace，使用旧的路径结构
            self.base_dir = Path.cwd() / "subagents" / self.subagent_name
            logger.warning(
                f"FileContext initialized without session_workspace, "
                f"using legacy path: {self.base_dir}"
            )

        # 默认可读：自己的工作目录 + session shared + global shared
        if not self.can_read:
            read_paths = [self.base_dir]
            if self.session_workspace:
                read_paths.append(self.session_workspace.shared_dir)  # Session-specific
                read_paths.append(self.session_workspace.workspace_root / "shared")  # Global
            else:
                read_paths.append(Path.cwd() / "shared")  # Legacy
            self.can_read = read_paths

        # 默认可写：scratch/ 和 logs/
        if not self.can_write:
            self.can_write = [
                self.base_dir / "scratch",
                self.base_dir / "logs",
            ]

        # 确保工作目录存在
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """确保必要的目录存在"""
        for subdir in ["scratch", "logs", "scripts"]:
            (self.base_dir / subdir).mkdir(parents=True, exist_ok=True)

    def _check_read_access(self, path: Path) -> bool:
        """检查读取权限

        Args:
            path: 目标路径

        Returns:
            是否有读取权限
        """
        abs_path = path if path.is_absolute() else path.resolve()
        for allowed in self.can_read:
            allowed_abs = allowed if allowed.is_absolute() else allowed.resolve()
            try:
                abs_path.relative_to(allowed_abs)
                return True
            except ValueError:
                continue
        return False

    def _check_write_access(self, path: Path) -> bool:
        """检查写入权限

        Args:
            path: 目标路径

        Returns:
            是否有写入权限
        """
        abs_path = path if path.is_absolute() else path.resolve()
        for allowed in self.can_write:
            allowed_abs = allowed if allowed.is_absolute() else allowed.resolve()
            try:
                abs_path.relative_to(allowed_abs)
                return True
            except ValueError:
                continue
        return False

    # ==================== 同步 API ====================

    def read_skill(self) -> str:
        """读取 SKILL.md 技能说明

        Returns:
            SKILL.md 的内容

        Raises:
            FileNotFoundInContextError: SKILL.md 不存在
        """
        skill_path = self.base_dir / "SKILL.md"
        if not skill_path.exists():
            raise FileNotFoundInContextError(f"SKILL.md not found at {skill_path}")
        return skill_path.read_text(encoding="utf-8")

    def read_scratch(self, filename: str) -> str:
        """读取 scratch 目录中的文件

        Args:
            filename: 文件名

        Returns:
            文件内容

        Raises:
            FileNotFoundInContextError: 文件不存在
        """
        file_path = self.base_dir / "scratch" / filename
        if not file_path.exists():
            raise FileNotFoundInContextError(f"File not found: {file_path}")
        return file_path.read_text(encoding="utf-8")

    def write_scratch(self, filename: str, content: str) -> Path:
        """写入 scratch 目录

        Args:
            filename: 文件名
            content: 文件内容

        Returns:
            写入的文件路径

        Raises:
            FileAccessError: 无写入权限
        """
        file_path = self.base_dir / "scratch" / filename
        if not self._check_write_access(file_path):
            raise FileAccessError(f"No write access to {file_path}")

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        logger.debug(f"[{self.subagent_name}] Wrote to {file_path}")
        return file_path

    def read_shared(self, path: str) -> str:
        """读取共享资源

        Args:
            path: 相对于 shared/ 的路径

        Returns:
            文件内容

        Raises:
            FileAccessError: 无读取权限
            FileNotFoundInContextError: 文件不存在
        """
        # Try session-specific shared first, then global shared
        if self.session_workspace:
            file_path = self.session_workspace.shared_dir / path
            if not file_path.exists():
                file_path = self.session_workspace.workspace_root / "shared" / path
        else:
            # Legacy path
            file_path = Path.cwd() / "shared" / path

        if not self._check_read_access(file_path):
            raise FileAccessError(f"No read access to {file_path}")
        if not file_path.exists():
            raise FileNotFoundInContextError(f"Shared file not found: {file_path}")
        return file_path.read_text(encoding="utf-8")

    def get_plan(self) -> dict[str, Any]:
        """读取 Coordinator 下发的任务规划

        Returns:
            plan.md 解析后的字典（支持 JSON 或 YAML 格式的 front matter）

        Raises:
            FileNotFoundInContextError: plan.md 不存在
        """
        # Try session-specific coordinator directory first
        if self.session_workspace:
            plan_path = self.session_workspace.coordinator_dir / "plan.md"
        else:
            # Legacy path
            plan_path = Path.cwd() / "coordinator" / "plan.md"

        if not plan_path.exists():
            raise FileNotFoundInContextError(f"Plan not found: {plan_path}")

        content = plan_path.read_text(encoding="utf-8")

        # 尝试解析 JSON front matter
        if content.startswith("```json"):
            try:
                json_block = content.split("```json")[1].split("```")[0]
                return json.loads(json_block)
            except (IndexError, json.JSONDecodeError):
                pass

        # 返回原始内容
        return {"raw_content": content}

    def update_todo(self, items: list[str]) -> None:
        """更新待办事项

        Args:
            items: 待办事项列表
        """
        todo_path = self.base_dir / "scratch" / "todo.md"
        content = "# TODO\n\n"
        for i, item in enumerate(items, 1):
            content += f"{i}. [ ] {item}\n"
        self.write_scratch("todo.md", content)

    def log(self, message: str, level: str = "info") -> None:
        """记录日志

        Args:
            message: 日志消息
            level: 日志级别（info, warning, error, debug）
        """
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] [{level.upper()}] {message}\n"

        log_file = self.base_dir / "logs" / f"{datetime.now().strftime('%Y-%m-%d')}.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        with log_file.open("a", encoding="utf-8") as f:
            f.write(log_entry)

        # 同时使用 loguru 输出
        getattr(logger, level, logger.info)(f"[{self.subagent_name}] {message}")

    def list_scratch(self) -> list[str]:
        """列出 scratch 目录中的文件

        Returns:
            文件名列表
        """
        scratch_dir = self.base_dir / "scratch"
        if not scratch_dir.exists():
            return []
        return [f.name for f in scratch_dir.iterdir() if f.is_file()]

    def clear_scratch(self) -> None:
        """清空 scratch 目录"""
        scratch_dir = self.base_dir / "scratch"
        if scratch_dir.exists():
            for f in scratch_dir.iterdir():
                if f.is_file():
                    f.unlink()
            logger.debug(f"[{self.subagent_name}] Cleared scratch directory")

    # ==================== 异步 API ====================

    async def aread_scratch(self, filename: str) -> str:
        """异步读取 scratch 目录中的文件

        Args:
            filename: 文件名

        Returns:
            文件内容

        Raises:
            FileNotFoundInContextError: 文件不存在
        """
        file_path = self.base_dir / "scratch" / filename
        if not file_path.exists():
            raise FileNotFoundInContextError(f"File not found: {file_path}")

        if HAS_AIOFILES:
            async with aiofiles.open(file_path, encoding="utf-8") as f:
                return await f.read()
        else:
            # 回退到同步读取
            return file_path.read_text(encoding="utf-8")

    async def awrite_scratch(self, filename: str, content: str) -> Path:
        """异步写入 scratch 目录

        Args:
            filename: 文件名
            content: 文件内容

        Returns:
            写入的文件路径

        Raises:
            FileAccessError: 无写入权限
        """
        file_path = self.base_dir / "scratch" / filename
        if not self._check_write_access(file_path):
            raise FileAccessError(f"No write access to {file_path}")

        file_path.parent.mkdir(parents=True, exist_ok=True)

        if HAS_AIOFILES:
            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(content)
        else:
            # 回退到同步写入
            file_path.write_text(content, encoding="utf-8")

        logger.debug(f"[{self.subagent_name}] Wrote to {file_path}")
        return file_path

    async def alog(self, message: str, level: str = "info") -> None:
        """异步记录日志

        Args:
            message: 日志消息
            level: 日志级别
        """
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] [{level.upper()}] {message}\n"

        log_file = self.base_dir / "logs" / f"{datetime.now().strftime('%Y-%m-%d')}.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        if HAS_AIOFILES:
            async with aiofiles.open(log_file, "a", encoding="utf-8") as f:
                await f.write(log_entry)
        else:
            # 回退到同步写入
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)

        getattr(logger, level, logger.info)(f"[{self.subagent_name}] {message}")

    # ==================== 工具方法 ====================

    def get_scratch_path(self, filename: str) -> Path:
        """获取 scratch 目录中文件的完整路径

        Args:
            filename: 文件名

        Returns:
            完整路径
        """
        return self.base_dir / "scratch" / filename

    def exists_in_scratch(self, filename: str) -> bool:
        """检查 scratch 目录中是否存在文件

        Args:
            filename: 文件名

        Returns:
            是否存在
        """
        return (self.base_dir / "scratch" / filename).exists()

    def __repr__(self) -> str:
        return (
            f"FileContext("
            f"subagent_name={self.subagent_name!r}, "
            f"base_dir={self.base_dir!r})"
        )
