"""Unified workspace management for RegReader.

This package provides a unified workspace architecture where all agent execution
state is organized under a single configurable root directory with session-level
subdirectories.

Key Components:
- SessionWorkspace: Abstraction for a single session's workspace
- WorkspaceManager: Core workspace management and lifecycle
- WorkspaceMigrator: Migration from legacy to unified structure
- LegacyWorkspaceAdapter: Backward compatibility layer

Example:
    >>> from regreader.workspace import WorkspaceManager
    >>> manager = WorkspaceManager(Path(".regreader_workspace"))
    >>> session = manager.create_session()
    >>> print(session.coordinator_dir)
    .regreader_workspace/sessions/session_20260122_103045/coordinator
"""

from regreader.workspace.compat import (
    LegacyWorkspaceAdapter,
    check_and_warn_legacy,
    get_workspace_path,
)
from regreader.workspace.manager import WorkspaceManager
from regreader.workspace.migrator import MigrationReport, WorkspaceMigrator
from regreader.workspace.session import SessionWorkspace

__all__ = [
    "WorkspaceManager",
    "SessionWorkspace",
    "WorkspaceMigrator",
    "MigrationReport",
    "LegacyWorkspaceAdapter",
    "check_and_warn_legacy",
    "get_workspace_path",
]
