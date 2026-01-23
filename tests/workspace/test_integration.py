"""Integration tests for unified workspace architecture.

Tests end-to-end workflows combining multiple workspace components.
"""

import json
from pathlib import Path

import pytest

from regreader.workspace import (
    LegacyWorkspaceAdapter,
    WorkspaceManager,
    WorkspaceMigrator,
)
from regreader.workspace.session import SessionWorkspace


class TestWorkspaceIntegration:
    """Integration tests for workspace components."""

    @pytest.fixture
    def legacy_project(self, tmp_path):
        """Create a complete legacy project structure."""
        # Create legacy sessions with realistic content
        for i, session_id in enumerate(
            [
                "session_20260118_043822",
                "session_20260119_172514",
                "session_20260122_103045",
            ]
        ):
            session_dir = tmp_path / "coordinator" / session_id
            session_dir.mkdir(parents=True)

            # Create realistic session files
            (session_dir / "plan.md").write_text(
                f"# Session Plan\n\nQuery: Test query {i}\n"
            )
            (session_dir / "session_state.json").write_text(
                json.dumps(
                    {
                        "session_id": session_id,
                        "query_count": i + 1,
                        "current_reg_id": "angui_2024",
                    }
                )
            )
            (session_dir / "call_stack.json").write_text(json.dumps([]))

            # Create logs
            logs_dir = session_dir / "logs"
            logs_dir.mkdir()
            (logs_dir / "events.jsonl").write_text(
                f'{{"event_type": "task_started", "session_id": "{session_id}"}}\n'
            )

        # Create subagent workspaces
        for subagent in ["regsearch", "search", "table", "reference"]:
            subagent_dir = tmp_path / "subagents" / subagent
            subagent_dir.mkdir(parents=True)

            (subagent_dir / "SKILL.md").write_text(f"# {subagent.title()} Skill\n")

            scratch_dir = subagent_dir / "scratch"
            scratch_dir.mkdir()
            (scratch_dir / "results.json").write_text(json.dumps({"results": []}))

            logs_dir = subagent_dir / "logs"
            logs_dir.mkdir()
            (logs_dir / "debug.log").write_text(f"{subagent} debug log\n")

        # Create shared resources
        shared_dir = tmp_path / "shared"
        shared_dir.mkdir()
        (shared_dir / "README.md").write_text("# Shared Resources\n")

        docs_dir = shared_dir / "docs"
        docs_dir.mkdir()
        (docs_dir / "guide.md").write_text("# User Guide\n")

        return tmp_path

    def test_complete_migration_workflow(self, legacy_project):
        """Test complete migration from legacy to unified workspace."""
        # Step 1: Detect legacy structure
        adapter = LegacyWorkspaceAdapter(legacy_project)
        assert adapter.has_legacy is True

        legacy_sessions = adapter.list_legacy_sessions()
        assert len(legacy_sessions) == 3

        # Step 2: Create workspace manager
        workspace_root = legacy_project / ".regreader_workspace"
        manager = WorkspaceManager(workspace_root)

        # Step 3: Create migrator
        migrator = WorkspaceMigrator(manager)
        migrator.project_root = legacy_project

        # Step 4: Migrate all sessions
        reports = migrator.migrate_all_sessions(dry_run=False, backup=True)

        assert len(reports) == 3
        assert all(r.success for r in reports)

        # Step 5: Verify new structure
        for session_id in legacy_sessions:
            session = manager.get_session(session_id)

            # Check coordinator files
            assert (session.coordinator_dir / "plan.md").exists()
            assert (session.coordinator_dir / "session_state.json").exists()
            assert (session.coordinator_dir / "logs" / "events.jsonl").exists()

        # Step 6: Migrate shared resources
        success = migrator.migrate_shared_resources(dry_run=False)
        assert success is True

        shared_path = manager.shared_dir / "docs" / "guide.md"
        assert shared_path.exists()

        # Step 7: Verify backups created
        backup_dir = legacy_project / "backups"
        assert backup_dir.exists()
        backup_files = list(backup_dir.glob("*.tar.gz"))
        assert len(backup_files) == 3

    def test_mixed_structure_operation(self, legacy_project):
        """Test operating with both legacy and new structures."""
        # Create new workspace
        workspace_root = legacy_project / ".regreader_workspace"
        manager = WorkspaceManager(workspace_root)

        # Create new session
        new_session = manager.create_session("session_20260123_120000")

        # Adapter should handle both
        adapter = LegacyWorkspaceAdapter(legacy_project)

        # Get legacy session
        legacy_path = adapter.get_session_dir("session_20260122_103045")
        assert legacy_path == legacy_project / "coordinator" / "session_20260122_103045"

        # Get new session
        new_path = adapter.get_session_dir("session_20260123_120000")
        assert (
            new_path
            == workspace_root / "sessions" / "session_20260123_120000"
        )

    def test_workspace_lifecycle(self, tmp_path):
        """Test complete workspace lifecycle."""
        manager = WorkspaceManager(tmp_path)

        # Create sessions
        session1 = manager.create_session("session_20260122_103045")
        session2 = manager.create_session("session_20260122_104530")
        session3 = manager.create_session("session_20260122_105612")

        # Add content to sessions
        for session in [session1, session2, session3]:
            (session.coordinator_dir / "plan.md").write_text("# Plan\n")
            (session.coordinator_dir / "logs" / "events.jsonl").write_text("")

        # List sessions
        sessions = manager.list_sessions()
        assert len(sessions) == 3

        # Set active session
        manager.set_active_session("session_20260122_104530")
        active = manager.get_active_session()
        assert active.session_id == "session_20260122_104530"

        # Archive old session
        archive_path = manager.archive_session("session_20260122_103045")
        assert archive_path.exists()
        assert not session1.session_dir.exists()

        # List sessions (should be 2 active)
        sessions = manager.list_sessions()
        assert len(sessions) == 2

        # List with archived
        all_sessions = manager.list_sessions(include_archived=True)
        assert len(all_sessions) == 3

    def test_session_workspace_integration(self, tmp_path):
        """Test SessionWorkspace integration with other components."""
        manager = WorkspaceManager(tmp_path)
        session = manager.create_session("session_20260122_103045")

        # Create realistic session structure
        (session.coordinator_dir / "plan.md").write_text("# Plan\n")
        (session.coordinator_dir / "session_state.json").write_text("{}")

        # Create subagent workspaces
        for subagent in ["regsearch", "search", "table"]:
            subagent_dir = session.get_subagent_dir(subagent)
            subagent_dir.mkdir(parents=True)
            (subagent_dir / "scratch").mkdir()
            (subagent_dir / "logs").mkdir()

        # Create shared resources
        (session.shared_dir / "data.json").write_text("{}")

        # Verify structure
        assert session.coordinator_dir.exists()
        assert session.subagents_dir.exists()
        assert session.shared_dir.exists()
        assert session.logs_dir.exists()

        # Verify subagent directories
        for subagent in ["regsearch", "search", "table"]:
            subagent_dir = session.get_subagent_dir(subagent)
            assert subagent_dir.exists()
            assert (subagent_dir / "scratch").exists()
            assert (subagent_dir / "logs").exists()

    def test_migration_with_rollback(self, legacy_project):
        """Test migration with rollback capability."""
        workspace_root = legacy_project / ".regreader_workspace"
        manager = WorkspaceManager(workspace_root)
        migrator = WorkspaceMigrator(manager)
        migrator.project_root = legacy_project

        # Migrate one session
        session_id = "session_20260122_103045"
        report = migrator.migrate_session(session_id, dry_run=False, backup=True)
        assert report.success is True

        # Verify migration
        session = manager.get_session(session_id)
        assert session.coordinator_dir.exists()

        # Rollback
        success = migrator.rollback_migration(session_id)
        assert success is True

        # Verify rollback
        with pytest.raises(FileNotFoundError):
            manager.get_session(session_id)

        # Original should still exist
        original = legacy_project / "coordinator" / session_id
        assert original.exists()

    def test_adapter_path_resolution_priority(self, tmp_path):
        """Test adapter prioritizes new structure over legacy."""
        # Create both structures
        legacy_session = tmp_path / "coordinator" / "session_20260122_103045"
        legacy_session.mkdir(parents=True)
        (legacy_session / "legacy.txt").write_text("legacy")

        new_session = (
            tmp_path / ".regreader_workspace" / "sessions" / "session_20260122_103045"
        )
        new_session.mkdir(parents=True)
        (new_session / "new.txt").write_text("new")

        adapter = LegacyWorkspaceAdapter(tmp_path)

        # Should prefer new structure
        session_dir = adapter.get_session_dir("session_20260122_103045")
        assert session_dir == new_session
        assert (session_dir / "new.txt").exists()

    def test_workspace_cleanup_integration(self, tmp_path):
        """Test workspace cleanup with archiving."""
        manager = WorkspaceManager(tmp_path)

        # Create sessions with different ages
        import os
        from datetime import datetime, timedelta

        old_session = manager.create_session("session_20260115_103045")
        new_session = manager.create_session("session_20260122_103045")

        # Make old session actually old
        old_time = datetime.now() - timedelta(days=10)
        os.utime(
            old_session.session_dir, (old_time.timestamp(), old_time.timestamp())
        )

        # Cleanup (7 days retention)
        archived = manager.cleanup_old_sessions(retention_days=7, dry_run=False)

        assert len(archived) == 1
        assert archived[0] == "session_20260115_103045"

        # Old session should be archived
        assert not old_session.session_dir.exists()

        # New session should remain
        assert new_session.session_dir.exists()

        # Archive should exist
        archive_files = list(manager.archive_dir.rglob("*.tar.gz"))
        assert len(archive_files) == 1

    def test_concurrent_workspace_access(self, tmp_path):
        """Test multiple WorkspaceManager instances accessing same workspace."""
        # Create first manager and session
        manager1 = WorkspaceManager(tmp_path)
        session1 = manager1.create_session("session_20260122_103045")
        (session1.coordinator_dir / "data.txt").write_text("data")

        # Create second manager instance
        manager2 = WorkspaceManager(tmp_path)

        # Should see session created by first manager
        sessions = manager2.list_sessions()
        assert "session_20260122_103045" in sessions

        # Should be able to access session
        session2 = manager2.get_session("session_20260122_103045")
        assert (session2.coordinator_dir / "data.txt").read_text() == "data"

    def test_migration_preserves_permissions(self, legacy_project):
        """Test migration preserves file permissions."""
        import os
        import stat

        # Create file with specific permissions
        session_dir = legacy_project / "coordinator" / "session_20260122_103045"
        test_file = session_dir / "executable.sh"
        test_file.write_text("#!/bin/bash\necho test\n")
        test_file.chmod(0o755)

        original_mode = test_file.stat().st_mode

        # Migrate
        workspace_root = legacy_project / ".regreader_workspace"
        manager = WorkspaceManager(workspace_root)
        migrator = WorkspaceMigrator(manager)
        migrator.project_root = legacy_project

        migrator.migrate_session("session_20260122_103045", dry_run=False, backup=False)

        # Check permissions preserved
        new_file = (
            workspace_root
            / "sessions"
            / "session_20260122_103045"
            / "coordinator"
            / "executable.sh"
        )
        new_mode = new_file.stat().st_mode

        assert stat.S_IMODE(new_mode) == stat.S_IMODE(original_mode)

    def test_workspace_with_symlinks(self, tmp_path):
        """Test workspace handles symlinks correctly."""
        manager = WorkspaceManager(tmp_path)
        session = manager.create_session("session_20260122_103045")

        # Create symlink in shared directory
        target = tmp_path / "external_data"
        target.mkdir()
        (target / "data.json").write_text("{}")

        link = manager.shared_dir / "data"
        link.symlink_to(target)

        # Verify symlink works
        assert link.is_symlink()
        assert (link / "data.json").exists()

    def test_migration_summary_accuracy(self, legacy_project):
        """Test migration summary provides accurate information."""
        workspace_root = legacy_project / ".regreader_workspace"
        manager = WorkspaceManager(workspace_root)
        migrator = WorkspaceMigrator(manager)
        migrator.project_root = legacy_project

        # Get initial summary
        summary_before = migrator.get_migration_summary()
        assert summary_before["legacy_sessions_count"] == 3
        assert summary_before["migrated_sessions_count"] == 0

        # Migrate half
        migrator.migrate_session("session_20260122_103045", dry_run=False, backup=False)

        # Get updated summary
        summary_after = migrator.get_migration_summary()
        assert summary_after["legacy_sessions_count"] == 3  # Still in legacy
        assert summary_after["migrated_sessions_count"] == 1

        # Migrate all
        migrator.migrate_all_sessions(dry_run=False, backup=False)

        # Final summary
        summary_final = migrator.get_migration_summary()
        assert summary_final["migrated_sessions_count"] == 3
