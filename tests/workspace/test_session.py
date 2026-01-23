"""Tests for SessionWorkspace dataclass.

Tests the session workspace abstraction and path resolution.
"""

import pytest
from pathlib import Path

from regreader.workspace.session import SessionWorkspace


class TestSessionWorkspace:
    """Test SessionWorkspace dataclass."""

    def test_session_workspace_creation(self, tmp_path):
        """Test creating a SessionWorkspace instance."""
        session_id = "session_20260122_103045"
        workspace = SessionWorkspace(session_id, tmp_path)

        assert workspace.session_id == session_id
        assert workspace.workspace_root == tmp_path

    def test_session_dir_path(self, tmp_path):
        """Test session_dir property."""
        session_id = "session_20260122_103045"
        workspace = SessionWorkspace(session_id, tmp_path)

        expected = tmp_path / "sessions" / session_id
        assert workspace.session_dir == expected

    def test_coordinator_dir_path(self, tmp_path):
        """Test coordinator_dir property."""
        session_id = "session_20260122_103045"
        workspace = SessionWorkspace(session_id, tmp_path)

        expected = tmp_path / "sessions" / session_id / "coordinator"
        assert workspace.coordinator_dir == expected

    def test_subagents_dir_path(self, tmp_path):
        """Test subagents_dir property."""
        session_id = "session_20260122_103045"
        workspace = SessionWorkspace(session_id, tmp_path)

        expected = tmp_path / "sessions" / session_id / "subagents"
        assert workspace.subagents_dir == expected

    def test_shared_dir_path(self, tmp_path):
        """Test shared_dir property."""
        session_id = "session_20260122_103045"
        workspace = SessionWorkspace(session_id, tmp_path)

        expected = tmp_path / "sessions" / session_id / "shared"
        assert workspace.shared_dir == expected

    def test_logs_dir_path(self, tmp_path):
        """Test logs_dir property."""
        session_id = "session_20260122_103045"
        workspace = SessionWorkspace(session_id, tmp_path)

        expected = tmp_path / "sessions" / session_id / "coordinator" / "logs"
        assert workspace.logs_dir == expected

    def test_get_subagent_dir(self, tmp_path):
        """Test get_subagent_dir method."""
        session_id = "session_20260122_103045"
        workspace = SessionWorkspace(session_id, tmp_path)

        subagent_dir = workspace.get_subagent_dir("regsearch")
        expected = tmp_path / "sessions" / session_id / "subagents" / "regsearch"
        assert subagent_dir == expected

    def test_ensure_structure_creates_directories(self, tmp_path):
        """Test ensure_structure creates all required directories."""
        session_id = "session_20260122_103045"
        workspace = SessionWorkspace(session_id, tmp_path)

        # Directories should not exist yet
        assert not workspace.session_dir.exists()

        # Create structure
        workspace.ensure_structure()

        # All directories should now exist
        assert workspace.coordinator_dir.exists()
        assert workspace.subagents_dir.exists()
        assert workspace.shared_dir.exists()
        assert workspace.logs_dir.exists()

    def test_ensure_structure_idempotent(self, tmp_path):
        """Test ensure_structure can be called multiple times safely."""
        session_id = "session_20260122_103045"
        workspace = SessionWorkspace(session_id, tmp_path)

        # Create structure twice
        workspace.ensure_structure()
        workspace.ensure_structure()

        # Should still work without errors
        assert workspace.coordinator_dir.exists()
        assert workspace.subagents_dir.exists()

    def test_multiple_subagent_dirs(self, tmp_path):
        """Test getting multiple subagent directories."""
        session_id = "session_20260122_103045"
        workspace = SessionWorkspace(session_id, tmp_path)

        subagents = ["regsearch", "search", "table", "reference"]
        for subagent in subagents:
            subagent_dir = workspace.get_subagent_dir(subagent)
            expected = tmp_path / "sessions" / session_id / "subagents" / subagent
            assert subagent_dir == expected

    def test_session_workspace_with_absolute_path(self):
        """Test SessionWorkspace with absolute path."""
        session_id = "session_20260122_103045"
        workspace_root = Path("/tmp/test_workspace")
        workspace = SessionWorkspace(session_id, workspace_root)

        assert workspace.session_dir.is_absolute()
        assert workspace.coordinator_dir.is_absolute()

    def test_session_workspace_with_relative_path(self):
        """Test SessionWorkspace with relative path."""
        session_id = "session_20260122_103045"
        workspace_root = Path(".regreader_workspace")
        workspace = SessionWorkspace(session_id, workspace_root)

        # Paths should maintain relative nature
        assert not workspace.session_dir.is_absolute()
