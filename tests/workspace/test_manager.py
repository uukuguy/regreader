"""Tests for WorkspaceManager class.

Tests workspace lifecycle management, session creation, archiving, and cleanup.
"""

import json
import tarfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from regreader.workspace.manager import WorkspaceManager
from regreader.workspace.session import SessionWorkspace


class TestWorkspaceManager:
    """Test WorkspaceManager class."""

    def test_workspace_manager_creation(self, tmp_path):
        """Test creating a WorkspaceManager instance."""
        manager = WorkspaceManager(tmp_path)

        assert manager.workspace_root == tmp_path
        assert manager.sessions_dir == tmp_path / "sessions"
        assert manager.shared_dir == tmp_path / "shared"
        assert manager.archive_dir == tmp_path / "archive"

    def test_workspace_structure_created(self, tmp_path):
        """Test workspace structure is created on initialization."""
        manager = WorkspaceManager(tmp_path)

        assert manager.workspace_root.exists()
        assert manager.sessions_dir.exists()
        assert manager.shared_dir.exists()
        assert manager.archive_dir.exists()
        assert manager.metadata_file.exists()

    def test_create_session_with_id(self, tmp_path):
        """Test creating a session with specific ID."""
        manager = WorkspaceManager(tmp_path)
        session_id = "session_20260122_103045"

        session = manager.create_session(session_id)

        assert isinstance(session, SessionWorkspace)
        assert session.session_id == session_id
        assert session.session_dir.exists()
        assert session.coordinator_dir.exists()

    def test_create_session_auto_id(self, tmp_path):
        """Test creating a session with auto-generated ID."""
        manager = WorkspaceManager(tmp_path)

        session = manager.create_session()

        assert session.session_id.startswith("session_")
        assert session.session_dir.exists()

    def test_create_session_duplicate_id(self, tmp_path):
        """Test creating a session with duplicate ID raises error."""
        manager = WorkspaceManager(tmp_path)
        session_id = "session_20260122_103045"

        # Create first session
        manager.create_session(session_id)

        # Creating duplicate should raise error
        with pytest.raises(FileExistsError):
            manager.create_session(session_id)

    def test_get_session_existing(self, tmp_path):
        """Test getting an existing session."""
        manager = WorkspaceManager(tmp_path)
        session_id = "session_20260122_103045"

        # Create session
        created = manager.create_session(session_id)

        # Get session
        retrieved = manager.get_session(session_id)

        assert retrieved.session_id == created.session_id
        assert retrieved.session_dir == created.session_dir

    def test_get_session_nonexistent(self, tmp_path):
        """Test getting a nonexistent session raises error."""
        manager = WorkspaceManager(tmp_path)

        with pytest.raises(FileNotFoundError):
            manager.get_session("nonexistent_session")

    def test_list_sessions_empty(self, tmp_path):
        """Test listing sessions when none exist."""
        manager = WorkspaceManager(tmp_path)

        sessions = manager.list_sessions()

        assert sessions == []

    def test_list_sessions_multiple(self, tmp_path):
        """Test listing multiple sessions."""
        manager = WorkspaceManager(tmp_path)

        # Create multiple sessions
        session_ids = [
            "session_20260122_103045",
            "session_20260122_104530",
            "session_20260122_105612",
        ]
        for session_id in session_ids:
            manager.create_session(session_id)

        sessions = manager.list_sessions()

        assert len(sessions) == 3
        assert set(sessions) == set(session_ids)

    def test_set_active_session(self, tmp_path):
        """Test setting active session creates symlink."""
        manager = WorkspaceManager(tmp_path)
        session_id = "session_20260122_103045"

        manager.create_session(session_id)
        manager.set_active_session(session_id)

        active_link = manager.sessions_dir / "active"
        assert active_link.exists()
        assert active_link.is_symlink()
        assert active_link.resolve().name == session_id

    def test_get_active_session(self, tmp_path):
        """Test getting active session."""
        manager = WorkspaceManager(tmp_path)
        session_id = "session_20260122_103045"

        manager.create_session(session_id)
        manager.set_active_session(session_id)

        active = manager.get_active_session()

        assert active.session_id == session_id

    def test_get_active_session_none(self, tmp_path):
        """Test getting active session when none set."""
        manager = WorkspaceManager(tmp_path)

        active = manager.get_active_session()

        assert active is None

    def test_archive_session(self, tmp_path):
        """Test archiving a session."""
        manager = WorkspaceManager(tmp_path)
        session_id = "session_20260122_103045"

        # Create session with some files
        session = manager.create_session(session_id)
        (session.coordinator_dir / "test.txt").write_text("test content")

        # Archive session
        archive_path = manager.archive_session(session_id)

        # Session directory should be removed
        assert not session.session_dir.exists()

        # Archive should exist
        assert archive_path.exists()
        assert archive_path.suffix == ".gz"

        # Archive should contain session files
        with tarfile.open(archive_path, "r:gz") as tar:
            members = tar.getnames()
            assert any(session_id in name for name in members)

    def test_archive_nonexistent_session(self, tmp_path):
        """Test archiving a nonexistent session raises error."""
        manager = WorkspaceManager(tmp_path)

        with pytest.raises(FileNotFoundError):
            manager.archive_session("nonexistent_session")

    def test_cleanup_old_sessions_dry_run(self, tmp_path):
        """Test cleanup in dry run mode."""
        manager = WorkspaceManager(tmp_path)

        # Create old and new sessions
        old_session = manager.create_session("session_20260115_103045")
        new_session = manager.create_session("session_20260122_103045")

        # Modify old session timestamp
        old_time = datetime.now() - timedelta(days=10)
        old_session.session_dir.touch()
        import os
        os.utime(old_session.session_dir, (old_time.timestamp(), old_time.timestamp()))

        # Dry run cleanup (7 days retention)
        old_sessions = manager.cleanup_old_sessions(retention_days=7, dry_run=True)

        # Should identify old session
        assert len(old_sessions) == 1
        assert old_sessions[0] == "session_20260115_103045"

        # But should not actually archive
        assert old_session.session_dir.exists()

    def test_cleanup_old_sessions_execute(self, tmp_path):
        """Test cleanup execution."""
        manager = WorkspaceManager(tmp_path)

        # Create old session
        old_session = manager.create_session("session_20260115_103045")

        # Modify timestamp
        old_time = datetime.now() - timedelta(days=10)
        import os
        os.utime(old_session.session_dir, (old_time.timestamp(), old_time.timestamp()))

        # Execute cleanup
        archived = manager.cleanup_old_sessions(retention_days=7, dry_run=False)

        # Should archive old session
        assert len(archived) == 1
        assert not old_session.session_dir.exists()

    def test_get_shared_path(self, tmp_path):
        """Test getting shared resource path."""
        manager = WorkspaceManager(tmp_path)

        shared_path = manager.get_shared_path("docs/guide.md")

        expected = tmp_path / "shared" / "docs" / "guide.md"
        assert shared_path == expected

    def test_list_sessions_with_archived(self, tmp_path):
        """Test listing sessions including archived."""
        manager = WorkspaceManager(tmp_path)

        # Create and archive a session
        session_id = "session_20260122_103045"
        manager.create_session(session_id)
        manager.archive_session(session_id)

        # Create active session
        manager.create_session("session_20260122_104530")

        # List without archived
        active_sessions = manager.list_sessions(include_archived=False)
        assert len(active_sessions) == 1

        # List with archived
        all_sessions = manager.list_sessions(include_archived=True)
        assert len(all_sessions) == 2

    def test_metadata_file_updated(self, tmp_path):
        """Test metadata file is updated on operations."""
        manager = WorkspaceManager(tmp_path)

        # Create session
        manager.create_session("session_20260122_103045")

        # Check metadata
        metadata = json.loads(manager.metadata_file.read_text())
        assert "created_at" in metadata
        assert "last_updated" in metadata

    def test_workspace_manager_with_existing_workspace(self, tmp_path):
        """Test WorkspaceManager with existing workspace."""
        # Create workspace
        manager1 = WorkspaceManager(tmp_path)
        manager1.create_session("session_20260122_103045")

        # Create new manager instance
        manager2 = WorkspaceManager(tmp_path)

        # Should see existing session
        sessions = manager2.list_sessions()
        assert len(sessions) == 1
        assert sessions[0] == "session_20260122_103045"

    def test_concurrent_session_creation(self, tmp_path):
        """Test creating sessions with auto-generated IDs doesn't collide."""
        manager = WorkspaceManager(tmp_path)

        # Create multiple sessions rapidly
        sessions = []
        for _ in range(5):
            session = manager.create_session()
            sessions.append(session.session_id)

        # All should have unique IDs
        assert len(set(sessions)) == 5
