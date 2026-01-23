"""Backward compatibility layer for legacy workspace structure.

Provides adapters and utilities to support legacy workspace structure
during the transition to unified workspace architecture.
"""

from pathlib import Path

from loguru import logger


class LegacyWorkspaceAdapter:
    """Adapter for legacy workspace structure.

    Provides backward compatibility during transition from scattered
    workspace structure (coordinator/, subagents/, shared/) to unified
    workspace architecture (.regreader_workspace/).

    Example:
        >>> adapter = LegacyWorkspaceAdapter(Path.cwd())
        >>> if adapter.has_legacy:
        ...     session_dir = adapter.get_session_dir("session_20260122_103045")
        ...     print(f"Found session at: {session_dir}")
    """

    def __init__(self, project_root: Path):
        """Initialize the adapter.

        Args:
            project_root: Project root directory
        """
        self.project_root = Path(project_root)
        self.has_legacy = self._detect_legacy_structure()

    def _detect_legacy_structure(self) -> bool:
        """Detect if legacy structure exists.

        Returns:
            True if legacy structure detected
        """
        return (
            (self.project_root / "coordinator").exists()
            or (self.project_root / "subagents").exists()
            or (self.project_root / "shared").exists()
        )

    def get_session_dir(self, session_id: str) -> Path:
        """Get session directory (legacy or new).

        Tries new structure first, falls back to legacy if not found.

        Args:
            session_id: Session identifier

        Returns:
            Path to session directory
        """
        # Try new structure first
        new_path = self.project_root / ".regreader_workspace" / "sessions" / session_id
        if new_path.exists():
            return new_path

        # Fall back to legacy
        legacy_path = self.project_root / "coordinator" / session_id
        if legacy_path.exists():
            logger.debug(f"Using legacy session path: {legacy_path}")
            return legacy_path

        # Default to new structure (for creation)
        return new_path

    def get_coordinator_dir(self, session_id: str) -> Path:
        """Get coordinator directory for a session.

        Args:
            session_id: Session identifier

        Returns:
            Path to coordinator directory
        """
        session_dir = self.get_session_dir(session_id)

        # New structure: session_dir/coordinator/
        if session_dir.parent.parent.name == ".regreader_workspace":
            return session_dir / "coordinator"

        # Legacy structure: coordinator/session_id/ is already the coordinator dir
        return session_dir

    def get_subagent_dir(self, session_id: str, subagent_name: str) -> Path:
        """Get subagent directory for a session.

        Args:
            session_id: Session identifier
            subagent_name: Subagent name

        Returns:
            Path to subagent directory
        """
        session_dir = self.get_session_dir(session_id)

        # New structure: session_dir/subagents/subagent_name/
        if session_dir.parent.parent.name == ".regreader_workspace":
            return session_dir / "subagents" / subagent_name

        # Legacy structure: subagents/subagent_name/
        legacy_subagent = self.project_root / "subagents" / subagent_name
        if legacy_subagent.exists():
            logger.debug(f"Using legacy subagent path: {legacy_subagent}")
            return legacy_subagent

        # Default to new structure
        return session_dir / "subagents" / subagent_name

    def get_shared_dir(self, session_id: str | None = None) -> Path:
        """Get shared directory.

        Args:
            session_id: Optional session identifier for session-specific shared

        Returns:
            Path to shared directory
        """
        if session_id:
            session_dir = self.get_session_dir(session_id)

            # New structure: session_dir/shared/
            if session_dir.parent.parent.name == ".regreader_workspace":
                return session_dir / "shared"

        # Legacy structure or global shared: shared/
        legacy_shared = self.project_root / "shared"
        if legacy_shared.exists():
            logger.debug(f"Using legacy shared path: {legacy_shared}")
            return legacy_shared

        # Default to new global shared
        return self.project_root / ".regreader_workspace" / "shared"

    def get_logs_dir(self, session_id: str) -> Path:
        """Get logs directory for a session.

        Args:
            session_id: Session identifier

        Returns:
            Path to logs directory
        """
        coordinator_dir = self.get_coordinator_dir(session_id)

        # New structure: coordinator_dir/logs/
        if coordinator_dir.parent.parent.parent.name == ".regreader_workspace":
            return coordinator_dir / "logs"

        # Legacy structure: coordinator/session_id/logs/
        legacy_logs = coordinator_dir / "logs"
        if legacy_logs.exists():
            return legacy_logs

        # Default to new structure
        return coordinator_dir / "logs"

    def list_legacy_sessions(self) -> list[str]:
        """List all sessions in legacy structure.

        Returns:
            List of session IDs found in legacy coordinator/ directory
        """
        legacy_coordinator = self.project_root / "coordinator"
        if not legacy_coordinator.exists():
            return []

        sessions = []
        for item in legacy_coordinator.iterdir():
            if item.is_dir() and item.name.startswith("session_"):
                sessions.append(item.name)

        return sorted(sessions)

    def list_legacy_subagents(self) -> list[str]:
        """List all subagent workspaces in legacy structure.

        Returns:
            List of subagent names found in legacy subagents/ directory
        """
        legacy_subagents = self.project_root / "subagents"
        if not legacy_subagents.exists():
            return []

        subagents = []
        for item in legacy_subagents.iterdir():
            if item.is_dir():
                subagents.append(item.name)

        return sorted(subagents)

    def get_migration_status(self) -> dict[str, bool | int]:
        """Get migration status summary.

        Returns:
            Dictionary with migration status information
        """
        new_workspace = self.project_root / ".regreader_workspace"
        new_sessions = new_workspace / "sessions"

        legacy_sessions = self.list_legacy_sessions()
        new_session_count = 0
        if new_sessions.exists():
            new_session_count = sum(
                1 for item in new_sessions.iterdir() if item.is_dir()
            )

        return {
            "has_legacy_structure": self.has_legacy,
            "legacy_sessions_count": len(legacy_sessions),
            "new_sessions_count": new_session_count,
            "migration_needed": self.has_legacy and len(legacy_sessions) > 0,
            "new_workspace_exists": new_workspace.exists(),
        }


def check_and_warn_legacy(project_root: Path | None = None) -> bool:
    """Check for legacy structure and warn user.

    Args:
        project_root: Project root directory (defaults to current directory)

    Returns:
        True if legacy structure detected
    """
    if project_root is None:
        project_root = Path.cwd()

    adapter = LegacyWorkspaceAdapter(project_root)

    if adapter.has_legacy:
        status = adapter.get_migration_status()

        logger.warning(
            "Legacy workspace structure detected. "
            f"Found {status['legacy_sessions_count']} legacy sessions. "
            "Please run 'regreader workspace migrate' to upgrade. "
            "Legacy structure will be deprecated in version 2.0."
        )

        if status["new_workspace_exists"]:
            logger.info(
                f"New workspace already exists with {status['new_sessions_count']} sessions. "
                "You can continue using both structures during the transition."
            )

        return True

    return False


def get_workspace_path(
    session_id: str,
    path_type: str = "session",
    subagent_name: str | None = None,
    project_root: Path | None = None,
) -> Path:
    """Get workspace path with automatic legacy fallback.

    Convenience function for getting workspace paths with automatic
    detection of legacy vs new structure.

    Args:
        session_id: Session identifier
        path_type: Type of path to get (session, coordinator, subagent, shared, logs)
        subagent_name: Subagent name (required if path_type is "subagent")
        project_root: Project root directory (defaults to current directory)

    Returns:
        Path to requested workspace location

    Raises:
        ValueError: If path_type is invalid or required parameters are missing

    Example:
        >>> path = get_workspace_path("session_20260122_103045", "coordinator")
        >>> print(path)
        .regreader_workspace/sessions/session_20260122_103045/coordinator
    """
    if project_root is None:
        project_root = Path.cwd()

    adapter = LegacyWorkspaceAdapter(project_root)

    if path_type == "session":
        return adapter.get_session_dir(session_id)
    elif path_type == "coordinator":
        return adapter.get_coordinator_dir(session_id)
    elif path_type == "subagent":
        if subagent_name is None:
            raise ValueError("subagent_name is required for path_type='subagent'")
        return adapter.get_subagent_dir(session_id, subagent_name)
    elif path_type == "shared":
        return adapter.get_shared_dir(session_id)
    elif path_type == "logs":
        return adapter.get_logs_dir(session_id)
    else:
        raise ValueError(
            f"Invalid path_type: {path_type}. "
            "Must be one of: session, coordinator, subagent, shared, logs"
        )
