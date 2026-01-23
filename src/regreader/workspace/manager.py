"""Unified workspace management for RegReader.

Provides centralized management of workspace directories, session lifecycle,
and cleanup operations.
"""

import json
import shutil
import tarfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from loguru import logger

from regreader.workspace.session import SessionWorkspace


class WorkspaceManager:
    """Unified workspace management for RegReader.

    Manages the lifecycle of session workspaces, including creation, archiving,
    and cleanup. Provides a single point of control for all workspace operations.

    Directory Structure:
        <workspace_root>/
        ├── sessions/                    # Active sessions
        │   ├── session_20260122_103045/
        │   └── active -> session_20260122_103045/  # Symlink to active session
        ├── shared/                      # Global shared resources (read-only)
        │   ├── data -> ../../data/storage/
        │   ├── docs/
        │   ├── templates/
        │   └── skills/
        ├── archive/                     # Archived sessions
        │   └── 2026-01/
        │       └── session_20260118_043822.tar.gz
        └── workspace.json               # Workspace metadata

    Attributes:
        workspace_root: Root directory of the workspace
        sessions_dir: Directory containing all session workspaces
        shared_dir: Directory containing global shared resources
        archive_dir: Directory containing archived sessions
        metadata_file: Path to workspace metadata file

    Example:
        >>> manager = WorkspaceManager(Path(".regreader_workspace"))
        >>> session = manager.create_session()
        >>> print(session.session_id)
        session_20260122_103045
    """

    def __init__(self, workspace_root: Path, session_id: str | None = None):
        """Initialize the workspace manager.

        Args:
            workspace_root: Root directory for all workspace data
            session_id: Optional session ID (for resuming existing session)
        """
        self.workspace_root = Path(workspace_root)
        self.sessions_dir = self.workspace_root / "sessions"
        self.shared_dir = self.workspace_root / "shared"
        self.archive_dir = self.workspace_root / "archive"
        self.metadata_file = self.workspace_root / "workspace.json"

        # Ensure workspace structure exists
        self._ensure_workspace_structure()

        logger.debug(f"WorkspaceManager initialized at {self.workspace_root}")

    def _ensure_workspace_structure(self) -> None:
        """Ensure the workspace directory structure exists."""
        try:
            self.sessions_dir.mkdir(parents=True, exist_ok=True)
            self.shared_dir.mkdir(parents=True, exist_ok=True)
            self.archive_dir.mkdir(parents=True, exist_ok=True)

            # Initialize metadata file if it doesn't exist
            if not self.metadata_file.exists():
                self._save_metadata({
                    "created_at": datetime.now().isoformat(),
                    "version": "1.0",
                    "active_session": None,
                })

            logger.debug("Workspace structure ensured")
        except OSError as e:
            logger.error(f"Failed to create workspace structure: {e}")
            raise

    def _load_metadata(self) -> dict[str, Any]:
        """Load workspace metadata from file."""
        try:
            with open(self.metadata_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load metadata: {e}, using defaults")
            return {
                "created_at": datetime.now().isoformat(),
                "version": "1.0",
                "active_session": None,
            }

    def _save_metadata(self, metadata: dict[str, Any]) -> None:
        """Save workspace metadata to file."""
        try:
            with open(self.metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
        except OSError as e:
            logger.error(f"Failed to save metadata: {e}")
            raise

    def create_session(self, session_id: str | None = None) -> SessionWorkspace:
        """Create a new session workspace.

        Args:
            session_id: Optional session ID. If not provided, generates one
                       based on current timestamp (format: session_YYYYMMDD_HHMMSS)

        Returns:
            SessionWorkspace instance for the new session

        Example:
            >>> manager = WorkspaceManager(Path(".regreader_workspace"))
            >>> session = manager.create_session()
            >>> print(session.session_id)
            session_20260122_103045
        """
        if session_id is None:
            session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        session = SessionWorkspace(session_id, self.workspace_root)
        session.ensure_structure()

        logger.info(f"Created session workspace: {session_id}")
        return session

    def get_session(self, session_id: str) -> SessionWorkspace:
        """Get an existing session workspace.

        Args:
            session_id: Session ID to retrieve

        Returns:
            SessionWorkspace instance

        Raises:
            FileNotFoundError: If session does not exist
        """
        session = SessionWorkspace(session_id, self.workspace_root)
        if not session.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")
        return session

    def list_sessions(self, include_archived: bool = False) -> list[str]:
        """List all session IDs in the workspace.

        Args:
            include_archived: Whether to include archived sessions

        Returns:
            List of session IDs
        """
        sessions = []

        # List active sessions
        if self.sessions_dir.exists():
            for item in self.sessions_dir.iterdir():
                if item.is_dir() and item.name.startswith("session_"):
                    sessions.append(item.name)

        # List archived sessions if requested
        if include_archived and self.archive_dir.exists():
            for year_month_dir in self.archive_dir.iterdir():
                if year_month_dir.is_dir():
                    for archive_file in year_month_dir.glob("session_*.tar.gz"):
                        session_id = archive_file.stem
                        sessions.append(f"{session_id} (archived)")

        return sorted(sessions)

    def get_active_session(self) -> SessionWorkspace | None:
        """Get the currently active session workspace.

        Returns:
            SessionWorkspace instance if active session exists, None otherwise
        """
        metadata = self._load_metadata()
        active_session_id = metadata.get("active_session")

        if active_session_id:
            try:
                return self.get_session(active_session_id)
            except FileNotFoundError:
                logger.warning(f"Active session {active_session_id} not found")
                return None
        return None

    def set_active_session(self, session_id: str) -> None:
        """Set the active session.

        Args:
            session_id: Session ID to set as active

        Raises:
            FileNotFoundError: If session does not exist
        """
        # Verify session exists
        session = self.get_session(session_id)

        # Update metadata
        metadata = self._load_metadata()
        metadata["active_session"] = session_id
        self._save_metadata(metadata)

        logger.info(f"Set active session: {session_id}")

    def archive_session(self, session_id: str) -> Path:
        """Archive a session workspace.

        Compresses the session directory into a tar.gz file and moves it
        to the archive directory organized by year-month.

        Args:
            session_id: Session ID to archive

        Returns:
            Path to the archived file

        Raises:
            FileNotFoundError: If session does not exist
        """
        session = self.get_session(session_id)
        session_dir = session.session_dir

        # Create year-month subdirectory in archive
        now = datetime.now()
        archive_subdir = self.archive_dir / f"{now.year}-{now.month:02d}"
        archive_subdir.mkdir(parents=True, exist_ok=True)

        # Create archive file
        archive_path = archive_subdir / f"{session_id}.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(session_dir, arcname=session_id)

        # Remove original session directory
        shutil.rmtree(session_dir)

        logger.info(f"Archived session {session_id} to {archive_path}")
        return archive_path

    def cleanup_old_sessions(self, retention_days: int) -> list[str]:
        """Clean up old sessions based on retention policy.

        Archives sessions older than the specified retention period.

        Args:
            retention_days: Number of days to retain sessions

        Returns:
            List of archived session IDs
        """
        archived_sessions = []
        cutoff_date = datetime.now() - timedelta(days=retention_days)

        if not self.sessions_dir.exists():
            return archived_sessions

        for session_dir in self.sessions_dir.iterdir():
            if not session_dir.is_dir() or not session_dir.name.startswith("session_"):
                continue

            # Check session age based on directory modification time
            mtime = datetime.fromtimestamp(session_dir.stat().st_mtime)
            if mtime < cutoff_date:
                try:
                    self.archive_session(session_dir.name)
                    archived_sessions.append(session_dir.name)
                except Exception as e:
                    logger.error(f"Failed to archive session {session_dir.name}: {e}")

        logger.info(f"Cleaned up {len(archived_sessions)} old sessions")
        return archived_sessions

    def get_shared_path(self, relative_path: str) -> Path:
        """Get path to a global shared resource.

        Args:
            relative_path: Relative path within shared directory

        Returns:
            Absolute path to the shared resource
        """
        return self.shared_dir / relative_path
