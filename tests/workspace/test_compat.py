"""Tests for LegacyWorkspaceAdapter class.

Tests backward compatibility layer for legacy workspace structure.
"""

from pathlib import Path

import pytest

from regreader.workspace.compat import (
    LegacyWorkspaceAdapter,
    check_and_warn_legacy,
    get_workspace_path,
)


class TestLegacyWorkspaceAdapter:
    """Test LegacyWorkspaceAdapter class."""

    @pytest.fixture
    def legacy_structure(self, tmp_path):
        """Create a legacy workspace structure."""
        # Create legacy directories
        (tmp_path / "coordinator" / "session_20260122_103045").mkdir(parents=True)
        (tmp_path / "subagents" / "regsearch").mkdir(parents=True)
        (tmp_path / "shared").mkdir(parents=True)
        return tmp_path

    @pytest.fixture
    def new_structure(self, tmp_path):
        """Create a new workspace structure."""
        session_dir = (
            tmp_path / ".regreader_workspace" / "sessions" / "session_20260122_103045"
        )
        (session_dir / "coordinator").mkdir(parents=True)
        (session_dir / "subagents" / "regsearch").mkdir(parents=True)
        (session_dir / "shared").mkdir(parents=True)
        return tmp_path

    def test_adapter_creation(self, tmp_path):
        """Test creating a LegacyWorkspaceAdapter instance."""
        adapter = LegacyWorkspaceAdapter(tmp_path)

        assert adapter.project_root == tmp_path

    def test_detect_legacy_structure_true(self, legacy_structure):
        """Test detecting legacy structure when it exists."""
        adapter = LegacyWorkspaceAdapter(legacy_structure)

        assert adapter.has_legacy is True

    def test_detect_legacy_structure_false(self, tmp_path):
        """Test detecting legacy structure when it doesn't exist."""
        adapter = LegacyWorkspaceAdapter(tmp_path)

        assert adapter.has_legacy is False

    def test_get_session_dir_new_structure(self, new_structure):
        """Test getting session directory from new structure."""
        adapter = LegacyWorkspaceAdapter(new_structure)

        session_dir = adapter.get_session_dir("session_20260122_103045")

        expected = (
            new_structure / ".regreader_workspace" / "sessions" / "session_20260122_103045"
        )
        assert session_dir == expected

    def test_get_session_dir_legacy_structure(self, legacy_structure):
        """Test getting session directory from legacy structure."""
        adapter = LegacyWorkspaceAdapter(legacy_structure)

        session_dir = adapter.get_session_dir("session_20260122_103045")

        expected = legacy_structure / "coordinator" / "session_20260122_103045"
        assert session_dir == expected

    def test_get_session_dir_nonexistent(self, tmp_path):
        """Test getting nonexistent session directory defaults to new structure."""
        adapter = LegacyWorkspaceAdapter(tmp_path)

        session_dir = adapter.get_session_dir("nonexistent_session")

        expected = tmp_path / ".regreader_workspace" / "sessions" / "nonexistent_session"
        assert session_dir == expected

    def test_get_coordinator_dir_new_structure(self, new_structure):
        """Test getting coordinator directory from new structure."""
        adapter = LegacyWorkspaceAdapter(new_structure)

        coordinator_dir = adapter.get_coordinator_dir("session_20260122_103045")

        expected = (
            new_structure
            / ".regreader_workspace"
            / "sessions"
            / "session_20260122_103045"
            / "coordinator"
        )
        assert coordinator_dir == expected

    def test_get_coordinator_dir_legacy_structure(self, legacy_structure):
        """Test getting coordinator directory from legacy structure."""
        adapter = LegacyWorkspaceAdapter(legacy_structure)

        coordinator_dir = adapter.get_coordinator_dir("session_20260122_103045")

        expected = legacy_structure / "coordinator" / "session_20260122_103045"
        assert coordinator_dir == expected

    def test_get_subagent_dir_new_structure(self, new_structure):
        """Test getting subagent directory from new structure."""
        adapter = LegacyWorkspaceAdapter(new_structure)

        subagent_dir = adapter.get_subagent_dir("session_20260122_103045", "regsearch")

        expected = (
            new_structure
            / ".regreader_workspace"
            / "sessions"
            / "session_20260122_103045"
            / "subagents"
            / "regsearch"
        )
        assert subagent_dir == expected

    def test_get_subagent_dir_legacy_structure(self, legacy_structure):
        """Test getting subagent directory from legacy structure."""
        adapter = LegacyWorkspaceAdapter(legacy_structure)

        subagent_dir = adapter.get_subagent_dir("session_20260122_103045", "regsearch")

        expected = legacy_structure / "subagents" / "regsearch"
        assert subagent_dir == expected

    def test_get_shared_dir_new_structure(self, new_structure):
        """Test getting shared directory from new structure."""
        adapter = LegacyWorkspaceAdapter(new_structure)

        shared_dir = adapter.get_shared_dir("session_20260122_103045")

        expected = (
            new_structure
            / ".regreader_workspace"
            / "sessions"
            / "session_20260122_103045"
            / "shared"
        )
        assert shared_dir == expected

    def test_get_shared_dir_legacy_structure(self, legacy_structure):
        """Test getting shared directory from legacy structure."""
        adapter = LegacyWorkspaceAdapter(legacy_structure)

        shared_dir = adapter.get_shared_dir()

        expected = legacy_structure / "shared"
        assert shared_dir == expected

    def test_get_logs_dir_new_structure(self, new_structure):
        """Test getting logs directory from new structure."""
        adapter = LegacyWorkspaceAdapter(new_structure)

        logs_dir = adapter.get_logs_dir("session_20260122_103045")

        expected = (
            new_structure
            / ".regreader_workspace"
            / "sessions"
            / "session_20260122_103045"
            / "coordinator"
            / "logs"
        )
        assert logs_dir == expected

    def test_get_logs_dir_legacy_structure(self, legacy_structure):
        """Test getting logs directory from legacy structure."""
        # Create logs directory
        logs_dir = (
            legacy_structure / "coordinator" / "session_20260122_103045" / "logs"
        )
        logs_dir.mkdir(parents=True)

        adapter = LegacyWorkspaceAdapter(legacy_structure)

        result = adapter.get_logs_dir("session_20260122_103045")

        assert result == logs_dir

    def test_list_legacy_sessions(self, legacy_structure):
        """Test listing legacy sessions."""
        # Create multiple sessions
        (legacy_structure / "coordinator" / "session_20260119_172514").mkdir()
        (legacy_structure / "coordinator" / "session_20260120_083045").mkdir()

        adapter = LegacyWorkspaceAdapter(legacy_structure)

        sessions = adapter.list_legacy_sessions()

        assert len(sessions) == 3
        assert "session_20260122_103045" in sessions
        assert "session_20260119_172514" in sessions
        assert "session_20260120_083045" in sessions

    def test_list_legacy_sessions_none(self, tmp_path):
        """Test listing legacy sessions when none exist."""
        adapter = LegacyWorkspaceAdapter(tmp_path)

        sessions = adapter.list_legacy_sessions()

        assert sessions == []

    def test_list_legacy_subagents(self, legacy_structure):
        """Test listing legacy subagent workspaces."""
        # Create multiple subagents
        (legacy_structure / "subagents" / "search").mkdir()
        (legacy_structure / "subagents" / "table").mkdir()

        adapter = LegacyWorkspaceAdapter(legacy_structure)

        subagents = adapter.list_legacy_subagents()

        assert len(subagents) == 3
        assert "regsearch" in subagents
        assert "search" in subagents
        assert "table" in subagents

    def test_get_migration_status_legacy(self, legacy_structure):
        """Test getting migration status with legacy structure."""
        adapter = LegacyWorkspaceAdapter(legacy_structure)

        status = adapter.get_migration_status()

        assert status["has_legacy_structure"] is True
        assert status["legacy_sessions_count"] == 1
        assert status["new_sessions_count"] == 0
        assert status["migration_needed"] is True
        assert status["new_workspace_exists"] is False

    def test_get_migration_status_new(self, new_structure):
        """Test getting migration status with new structure."""
        adapter = LegacyWorkspaceAdapter(new_structure)

        status = adapter.get_migration_status()

        assert status["has_legacy_structure"] is False
        assert status["legacy_sessions_count"] == 0
        assert status["new_sessions_count"] == 1
        assert status["migration_needed"] is False
        assert status["new_workspace_exists"] is True

    def test_get_migration_status_mixed(self, tmp_path):
        """Test getting migration status with mixed structure."""
        # Create both legacy and new
        (tmp_path / "coordinator" / "session_old").mkdir(parents=True)
        (
            tmp_path / ".regreader_workspace" / "sessions" / "session_new" / "coordinator"
        ).mkdir(parents=True)

        adapter = LegacyWorkspaceAdapter(tmp_path)

        status = adapter.get_migration_status()

        assert status["has_legacy_structure"] is True
        assert status["legacy_sessions_count"] == 1
        assert status["new_sessions_count"] == 1
        assert status["migration_needed"] is True
        assert status["new_workspace_exists"] is True


class TestCheckAndWarnLegacy:
    """Test check_and_warn_legacy function."""

    def test_check_and_warn_legacy_true(self, tmp_path):
        """Test check_and_warn_legacy returns True for legacy structure."""
        (tmp_path / "coordinator").mkdir()

        result = check_and_warn_legacy(tmp_path)

        assert result is True

    def test_check_and_warn_legacy_false(self, tmp_path):
        """Test check_and_warn_legacy returns False for no legacy structure."""
        result = check_and_warn_legacy(tmp_path)

        assert result is False

    def test_check_and_warn_legacy_default_path(self, monkeypatch):
        """Test check_and_warn_legacy with default path."""
        # This test would use current directory, so we'll just verify it doesn't crash
        result = check_and_warn_legacy()

        assert isinstance(result, bool)


class TestGetWorkspacePath:
    """Test get_workspace_path convenience function."""

    @pytest.fixture
    def new_structure(self, tmp_path):
        """Create a new workspace structure."""
        session_dir = (
            tmp_path / ".regreader_workspace" / "sessions" / "session_20260122_103045"
        )
        (session_dir / "coordinator").mkdir(parents=True)
        (session_dir / "subagents" / "regsearch").mkdir(parents=True)
        (session_dir / "shared").mkdir(parents=True)
        return tmp_path

    def test_get_workspace_path_session(self, new_structure):
        """Test getting session path."""
        path = get_workspace_path(
            "session_20260122_103045", "session", project_root=new_structure
        )

        expected = (
            new_structure / ".regreader_workspace" / "sessions" / "session_20260122_103045"
        )
        assert path == expected

    def test_get_workspace_path_coordinator(self, new_structure):
        """Test getting coordinator path."""
        path = get_workspace_path(
            "session_20260122_103045", "coordinator", project_root=new_structure
        )

        expected = (
            new_structure
            / ".regreader_workspace"
            / "sessions"
            / "session_20260122_103045"
            / "coordinator"
        )
        assert path == expected

    def test_get_workspace_path_subagent(self, new_structure):
        """Test getting subagent path."""
        path = get_workspace_path(
            "session_20260122_103045",
            "subagent",
            subagent_name="regsearch",
            project_root=new_structure,
        )

        expected = (
            new_structure
            / ".regreader_workspace"
            / "sessions"
            / "session_20260122_103045"
            / "subagents"
            / "regsearch"
        )
        assert path == expected

    def test_get_workspace_path_shared(self, new_structure):
        """Test getting shared path."""
        path = get_workspace_path(
            "session_20260122_103045", "shared", project_root=new_structure
        )

        expected = (
            new_structure
            / ".regreader_workspace"
            / "sessions"
            / "session_20260122_103045"
            / "shared"
        )
        assert path == expected

    def test_get_workspace_path_logs(self, new_structure):
        """Test getting logs path."""
        path = get_workspace_path(
            "session_20260122_103045", "logs", project_root=new_structure
        )

        expected = (
            new_structure
            / ".regreader_workspace"
            / "sessions"
            / "session_20260122_103045"
            / "coordinator"
            / "logs"
        )
        assert path == expected

    def test_get_workspace_path_invalid_type(self, new_structure):
        """Test getting workspace path with invalid type."""
        with pytest.raises(ValueError, match="Invalid path_type"):
            get_workspace_path(
                "session_20260122_103045", "invalid", project_root=new_structure
            )

    def test_get_workspace_path_subagent_missing_name(self, new_structure):
        """Test getting subagent path without subagent_name."""
        with pytest.raises(ValueError, match="subagent_name is required"):
            get_workspace_path(
                "session_20260122_103045", "subagent", project_root=new_structure
            )

    def test_get_workspace_path_default_project_root(self):
        """Test getting workspace path with default project root."""
        # Should use current directory without error
        path = get_workspace_path("session_20260122_103045", "session")

        assert isinstance(path, Path)
