"""Tests for WorkspaceMigrator class.

Tests migration from legacy scattered structure to unified workspace.
"""

import shutil
import tarfile
from pathlib import Path

import pytest

from regreader.workspace.manager import WorkspaceManager
from regreader.workspace.migrator import MigrationReport, WorkspaceMigrator


class TestWorkspaceMigrator:
    """Test WorkspaceMigrator class."""

    @pytest.fixture
    def legacy_structure(self, tmp_path):
        """Create a legacy workspace structure for testing."""
        # Create legacy directories
        coordinator_dir = tmp_path / "coordinator"
        subagents_dir = tmp_path / "subagents"
        shared_dir = tmp_path / "shared"

        # Create legacy sessions
        session_ids = [
            "session_20260118_043822",
            "session_20260119_172514",
            "session_20260122_103045",
        ]
        for session_id in session_ids:
            session_dir = coordinator_dir / session_id
            session_dir.mkdir(parents=True)
            (session_dir / "plan.md").write_text(f"# Plan for {session_id}")
            (session_dir / "session_state.json").write_text("{}")
            logs_dir = session_dir / "logs"
            logs_dir.mkdir()
            (logs_dir / "events.jsonl").write_text("")

        # Create legacy subagents
        for subagent in ["regsearch", "search", "table"]:
            subagent_dir = subagents_dir / subagent
            subagent_dir.mkdir(parents=True)
            (subagent_dir / "SKILL.md").write_text(f"# {subagent} skill")

        # Create shared resources
        shared_dir.mkdir(parents=True)
        (shared_dir / "README.md").write_text("# Shared resources")

        return tmp_path

    def test_migrator_creation(self, tmp_path):
        """Test creating a WorkspaceMigrator instance."""
        manager = WorkspaceManager(tmp_path / ".regreader_workspace")
        migrator = WorkspaceMigrator(manager)

        assert migrator.workspace_manager == manager
        assert migrator.project_root == Path.cwd()

    def test_detect_legacy_sessions(self, legacy_structure):
        """Test detecting legacy sessions."""
        manager = WorkspaceManager(legacy_structure / ".regreader_workspace")
        migrator = WorkspaceMigrator(manager)
        migrator.project_root = legacy_structure

        sessions = migrator.detect_legacy_sessions()

        assert len(sessions) == 3
        assert "session_20260118_043822" in sessions
        assert "session_20260119_172514" in sessions
        assert "session_20260122_103045" in sessions

    def test_detect_legacy_sessions_none(self, tmp_path):
        """Test detecting legacy sessions when none exist."""
        manager = WorkspaceManager(tmp_path / ".regreader_workspace")
        migrator = WorkspaceMigrator(manager)
        migrator.project_root = tmp_path

        sessions = migrator.detect_legacy_sessions()

        assert sessions == []

    def test_detect_legacy_subagents(self, legacy_structure):
        """Test detecting legacy subagent workspaces."""
        manager = WorkspaceManager(legacy_structure / ".regreader_workspace")
        migrator = WorkspaceMigrator(manager)
        migrator.project_root = legacy_structure

        subagents = migrator.detect_legacy_subagents()

        assert len(subagents) == 3
        assert "regsearch" in subagents
        assert "search" in subagents
        assert "table" in subagents

    def test_migrate_session_dry_run(self, legacy_structure):
        """Test migrating a session in dry run mode."""
        manager = WorkspaceManager(legacy_structure / ".regreader_workspace")
        migrator = WorkspaceMigrator(manager)
        migrator.project_root = legacy_structure

        report = migrator.migrate_session("session_20260122_103045", dry_run=True)

        assert isinstance(report, MigrationReport)
        assert report.session_id == "session_20260122_103045"
        assert report.success is True
        assert report.files_migrated > 0

        # Original should still exist
        old_path = legacy_structure / "coordinator" / "session_20260122_103045"
        assert old_path.exists()

    def test_migrate_session_execute(self, legacy_structure):
        """Test migrating a session with execution."""
        manager = WorkspaceManager(legacy_structure / ".regreader_workspace")
        migrator = WorkspaceMigrator(manager)
        migrator.project_root = legacy_structure

        report = migrator.migrate_session(
            "session_20260122_103045", dry_run=False, backup=False
        )

        assert report.success is True
        assert report.files_migrated > 0

        # New location should exist
        new_path = (
            legacy_structure
            / ".regreader_workspace"
            / "sessions"
            / "session_20260122_103045"
            / "coordinator"
        )
        assert new_path.exists()
        assert (new_path / "plan.md").exists()

    def test_migrate_session_with_backup(self, legacy_structure):
        """Test migrating a session with backup."""
        manager = WorkspaceManager(legacy_structure / ".regreader_workspace")
        migrator = WorkspaceMigrator(manager)
        migrator.project_root = legacy_structure

        report = migrator.migrate_session(
            "session_20260122_103045", dry_run=False, backup=True
        )

        assert report.success is True

        # Backup should exist
        backup_dir = legacy_structure / "backups"
        assert backup_dir.exists()
        backup_files = list(backup_dir.glob("session_20260122_103045_backup_*.tar.gz"))
        assert len(backup_files) == 1

        # Verify backup contents
        with tarfile.open(backup_files[0], "r:gz") as tar:
            members = tar.getnames()
            assert any("session_20260122_103045" in name for name in members)

    def test_migrate_session_nonexistent(self, legacy_structure):
        """Test migrating a nonexistent session."""
        manager = WorkspaceManager(legacy_structure / ".regreader_workspace")
        migrator = WorkspaceMigrator(manager)
        migrator.project_root = legacy_structure

        report = migrator.migrate_session("nonexistent_session", dry_run=False)

        assert report.success is False
        assert len(report.errors) > 0

    def test_migrate_all_sessions(self, legacy_structure):
        """Test migrating all sessions."""
        manager = WorkspaceManager(legacy_structure / ".regreader_workspace")
        migrator = WorkspaceMigrator(manager)
        migrator.project_root = legacy_structure

        reports = migrator.migrate_all_sessions(dry_run=False, backup=False)

        assert len(reports) == 3
        successful = sum(1 for r in reports if r.success)
        assert successful == 3

    def test_migrate_shared_resources(self, legacy_structure):
        """Test migrating shared resources."""
        manager = WorkspaceManager(legacy_structure / ".regreader_workspace")
        migrator = WorkspaceMigrator(manager)
        migrator.project_root = legacy_structure

        success = migrator.migrate_shared_resources(dry_run=False)

        assert success is True

        # Shared resources should be copied
        new_shared = legacy_structure / ".regreader_workspace" / "shared"
        assert new_shared.exists()
        assert (new_shared / "README.md").exists()

    def test_rollback_migration(self, legacy_structure):
        """Test rolling back a migration."""
        manager = WorkspaceManager(legacy_structure / ".regreader_workspace")
        migrator = WorkspaceMigrator(manager)
        migrator.project_root = legacy_structure

        # Migrate session
        migrator.migrate_session("session_20260122_103045", dry_run=False, backup=False)

        # Rollback
        success = migrator.rollback_migration("session_20260122_103045")

        assert success is True

        # New location should be removed
        new_path = (
            legacy_structure
            / ".regreader_workspace"
            / "sessions"
            / "session_20260122_103045"
        )
        assert not new_path.exists()

    def test_cleanup_legacy_structure(self, legacy_structure):
        """Test cleaning up legacy structure."""
        manager = WorkspaceManager(legacy_structure / ".regreader_workspace")
        migrator = WorkspaceMigrator(manager)
        migrator.project_root = legacy_structure

        # Migrate first
        migrator.migrate_all_sessions(dry_run=False, backup=False)

        # Cleanup
        results = migrator.cleanup_legacy_structure(
            remove_coordinator=True, remove_subagents=True, remove_shared=True
        )

        assert results["coordinator"] is True
        assert results["subagents"] is True
        assert results["shared"] is True

        # Legacy directories should be removed
        assert not (legacy_structure / "coordinator").exists()
        assert not (legacy_structure / "subagents").exists()
        assert not (legacy_structure / "shared").exists()

    def test_get_migration_summary(self, legacy_structure):
        """Test getting migration summary."""
        manager = WorkspaceManager(legacy_structure / ".regreader_workspace")
        migrator = WorkspaceMigrator(manager)
        migrator.project_root = legacy_structure

        summary = migrator.get_migration_summary()

        assert summary["legacy_sessions_count"] == 3
        assert summary["legacy_subagents_count"] == 3
        assert summary["migrated_sessions_count"] == 0

        # After migration
        migrator.migrate_all_sessions(dry_run=False, backup=False)
        summary = migrator.get_migration_summary()

        assert summary["migrated_sessions_count"] == 3

    def test_migration_report_to_dict(self):
        """Test MigrationReport to_dict method."""
        report = MigrationReport(
            session_id="session_20260122_103045",
            success=True,
            old_path=Path("/old/path"),
            new_path=Path("/new/path"),
            files_migrated=10,
            errors=[],
        )

        data = report.to_dict()

        assert data["session_id"] == "session_20260122_103045"
        assert data["success"] is True
        assert data["old_path"] == "/old/path"
        assert data["new_path"] == "/new/path"
        assert data["files_migrated"] == 10
        assert "timestamp" in data

    def test_migrate_preserves_file_structure(self, legacy_structure):
        """Test migration preserves directory structure."""
        manager = WorkspaceManager(legacy_structure / ".regreader_workspace")
        migrator = WorkspaceMigrator(manager)
        migrator.project_root = legacy_structure

        # Create nested structure
        session_dir = legacy_structure / "coordinator" / "session_20260122_103045"
        nested_dir = session_dir / "subdir" / "nested"
        nested_dir.mkdir(parents=True)
        (nested_dir / "file.txt").write_text("nested content")

        # Migrate
        migrator.migrate_session("session_20260122_103045", dry_run=False, backup=False)

        # Check nested structure preserved
        new_nested = (
            legacy_structure
            / ".regreader_workspace"
            / "sessions"
            / "session_20260122_103045"
            / "coordinator"
            / "subdir"
            / "nested"
            / "file.txt"
        )
        assert new_nested.exists()
        assert new_nested.read_text() == "nested content"

    def test_migrate_handles_empty_directories(self, legacy_structure):
        """Test migration handles empty directories."""
        manager = WorkspaceManager(legacy_structure / ".regreader_workspace")
        migrator = WorkspaceMigrator(manager)
        migrator.project_root = legacy_structure

        # Create empty directory
        session_dir = legacy_structure / "coordinator" / "session_20260122_103045"
        (session_dir / "empty_dir").mkdir()

        # Migrate
        report = migrator.migrate_session(
            "session_20260122_103045", dry_run=False, backup=False
        )

        assert report.success is True
