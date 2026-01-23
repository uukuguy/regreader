"""Session workspace abstraction.

Represents a single session's workspace with convenient path accessors.
"""

from dataclasses import dataclass
from pathlib import Path

from loguru import logger


@dataclass
class SessionWorkspace:
    """Represents a single session workspace.

    A session workspace contains all files and directories for a single
    agent execution session, organized under a session-specific directory.

    Directory Structure:
        <workspace_root>/sessions/<session_id>/
        ├── coordinator/          # Coordinator workspace
        │   ├── plan.md
        │   ├── session_state.json
        │   ├── call_stack.json
        │   └── logs/
        ├── subagents/           # Subagent workspaces
        │   ├── regsearch/
        │   ├── search/
        │   ├── table/
        │   └── reference/
        └── shared/              # Session-specific shared resources

    Attributes:
        session_id: Unique session identifier (e.g., "session_20260122_103045")
        workspace_root: Root directory of the workspace (e.g., ".regreader_workspace")

    Example:
        >>> workspace = SessionWorkspace("session_20260122_103045", Path(".regreader_workspace"))
        >>> workspace.ensure_structure()
        >>> print(workspace.coordinator_dir)
        .regreader_workspace/sessions/session_20260122_103045/coordinator
    """

    session_id: str
    workspace_root: Path

    @property
    def session_dir(self) -> Path:
        """Get the session directory path.

        Returns:
            Path to the session directory
        """
        return self.workspace_root / "sessions" / self.session_id

    @property
    def coordinator_dir(self) -> Path:
        """Get the coordinator workspace directory.

        Returns:
            Path to the coordinator directory
        """
        return self.session_dir / "coordinator"

    @property
    def subagents_dir(self) -> Path:
        """Get the subagents workspace directory.

        Returns:
            Path to the subagents directory
        """
        return self.session_dir / "subagents"

    @property
    def shared_dir(self) -> Path:
        """Get the session-specific shared directory.

        Returns:
            Path to the shared directory
        """
        return self.session_dir / "shared"

    @property
    def logs_dir(self) -> Path:
        """Get the logs directory.

        Returns:
            Path to the logs directory (under coordinator/)
        """
        return self.coordinator_dir / "logs"

    def get_subagent_dir(self, subagent_name: str) -> Path:
        """Get the workspace directory for a specific subagent.

        Args:
            subagent_name: Name of the subagent (e.g., "regsearch", "search")

        Returns:
            Path to the subagent's workspace directory

        Example:
            >>> workspace.get_subagent_dir("regsearch")
            .regreader_workspace/sessions/session_20260122_103045/subagents/regsearch
        """
        return self.subagents_dir / subagent_name

    def ensure_structure(self) -> None:
        """Create the session directory structure.

        Creates all necessary directories for the session workspace:
        - coordinator/
        - coordinator/logs/
        - subagents/
        - shared/

        This method is idempotent and safe to call multiple times.

        Raises:
            OSError: If directory creation fails due to permissions or disk space
        """
        try:
            self.coordinator_dir.mkdir(parents=True, exist_ok=True)
            self.subagents_dir.mkdir(parents=True, exist_ok=True)
            self.shared_dir.mkdir(parents=True, exist_ok=True)
            self.logs_dir.mkdir(parents=True, exist_ok=True)

            logger.debug(
                f"Session workspace structure ensured for session {self.session_id}"
            )
        except OSError as e:
            logger.error(
                f"Failed to create session workspace structure: {e}"
            )
            raise

    def exists(self) -> bool:
        """Check if the session workspace exists.

        Returns:
            True if the session directory exists, False otherwise
        """
        return self.session_dir.exists()

    def __str__(self) -> str:
        """String representation of the session workspace."""
        return f"SessionWorkspace(session_id={self.session_id}, path={self.session_dir})"

    def __repr__(self) -> str:
        """Detailed representation of the session workspace."""
        return f"SessionWorkspace(session_id='{self.session_id}', workspace_root={self.workspace_root})"
