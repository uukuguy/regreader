"""Workspace migration utility.

Provides tools to migrate from legacy scattered workspace structure
to the unified workspace architecture.
"""

import shutil
import tarfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from regreader.workspace.manager import WorkspaceManager


@dataclass
class MigrationReport:
    """Report for a single session migration.

    Attributes:
        session_id: Session identifier
        success: Whether migration succeeded
        old_path: Original session path
        new_path: New session path in unified workspace
        files_migrated: Number of files migrated
        errors: List of error messages encountered
        timestamp: Migration timestamp
    """

    session_id: str
    success: bool
    old_path: Path
    new_path: Path
    files_migrated: int = 0
    errors: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "session_id": self.session_id,
            "success": self.success,
            "old_path": str(self.old_path),
            "new_path": str(self.new_path),
            "files_migrated": self.files_migrated,
            "errors": self.errors,
            "timestamp": self.timestamp.isoformat(),
        }


class WorkspaceMigrator:
    """Migrate from scattered structure to unified workspace.

    Handles migration of:
    - coordinator/ sessions to .regreader_workspace/sessions/
    - subagents/ workspaces to session-specific subagent directories
    - Preserves all files and directory structure

    Example:
        >>> migrator = WorkspaceMigrator(workspace_manager)
        >>> sessions = migrator.detect_legacy_sessions()
        >>> for session_id in sessions:
        ...     report = migrator.migrate_session(session_id, dry_run=False)
        ...     print(f"Migrated {session_id}: {report.success}")
    """

    def __init__(self, workspace_manager: WorkspaceManager):
        """Initialize the migrator.

        Args:
            workspace_manager: WorkspaceManager instance for target workspace
        """
        self.workspace_manager = workspace_manager
        self.project_root = Path.cwd()
        self.legacy_coordinator_dir = self.project_root / "coordinator"
        self.legacy_subagents_dir = self.project_root / "subagents"
        self.legacy_shared_dir = self.project_root / "shared"

    def detect_legacy_sessions(self) -> list[str]:
        """Detect sessions in legacy coordinator/ directory.

        Returns:
            List of session IDs found in legacy structure
        """
        if not self.legacy_coordinator_dir.exists():
            return []

        sessions = []
        for item in self.legacy_coordinator_dir.iterdir():
            if item.is_dir() and item.name.startswith("session_"):
                sessions.append(item.name)

        logger.info(f"Detected {len(sessions)} legacy sessions")
        return sorted(sessions)

    def detect_legacy_subagents(self) -> list[str]:
        """Detect subagent workspaces in legacy subagents/ directory.

        Returns:
            List of subagent names found
        """
        if not self.legacy_subagents_dir.exists():
            return []

        subagents = []
        for item in self.legacy_subagents_dir.iterdir():
            if item.is_dir():
                subagents.append(item.name)

        logger.info(f"Detected {len(subagents)} legacy subagent workspaces")
        return sorted(subagents)

    def migrate_session(
        self,
        session_id: str,
        dry_run: bool = True,
        backup: bool = True,
    ) -> MigrationReport:
        """Migrate a single session to unified workspace.

        Args:
            session_id: Session ID to migrate
            dry_run: If True, only simulate migration without making changes
            backup: If True, create backup before migration

        Returns:
            MigrationReport with migration results
        """
        old_path = self.legacy_coordinator_dir / session_id
        if not old_path.exists():
            return MigrationReport(
                session_id=session_id,
                success=False,
                old_path=old_path,
                new_path=Path(""),
                errors=[f"Session directory not found: {old_path}"],
            )

        # Create session in new workspace
        try:
            session_workspace = self.workspace_manager.create_session(session_id)
            new_path = session_workspace.coordinator_dir
        except Exception as e:
            return MigrationReport(
                session_id=session_id,
                success=False,
                old_path=old_path,
                new_path=Path(""),
                errors=[f"Failed to create session workspace: {e}"],
            )

        report = MigrationReport(
            session_id=session_id,
            success=False,
            old_path=old_path,
            new_path=new_path,
        )

        if dry_run:
            logger.info(f"[DRY RUN] Would migrate {old_path} -> {new_path}")
            # Count files that would be migrated
            report.files_migrated = sum(1 for _ in old_path.rglob("*") if _.is_file())
            report.success = True
            return report

        try:
            # Create backup if requested
            if backup:
                self._create_backup(old_path, session_id)

            # Copy all files from old coordinator directory to new
            files_copied = 0
            for item in old_path.rglob("*"):
                if item.is_file():
                    rel_path = item.relative_to(old_path)
                    target = new_path / rel_path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, target)
                    files_copied += 1

            report.files_migrated = files_copied
            report.success = True

            logger.info(
                f"Migrated session {session_id}: {files_copied} files "
                f"from {old_path} to {new_path}"
            )

        except Exception as e:
            report.errors.append(f"Migration failed: {e}")
            logger.error(f"Failed to migrate session {session_id}: {e}")

        return report

    def migrate_all_sessions(
        self,
        dry_run: bool = True,
        backup: bool = True,
    ) -> list[MigrationReport]:
        """Migrate all legacy sessions.

        Args:
            dry_run: If True, only simulate migration
            backup: If True, create backups before migration

        Returns:
            List of MigrationReport for each session
        """
        sessions = self.detect_legacy_sessions()
        if not sessions:
            logger.info("No legacy sessions found to migrate")
            return []

        logger.info(f"Starting migration of {len(sessions)} sessions (dry_run={dry_run})")

        reports = []
        for session_id in sessions:
            report = self.migrate_session(session_id, dry_run=dry_run, backup=backup)
            reports.append(report)

        successful = sum(1 for r in reports if r.success)
        logger.info(
            f"Migration complete: {successful}/{len(reports)} sessions migrated successfully"
        )

        return reports

    def migrate_shared_resources(self, dry_run: bool = True) -> bool:
        """Migrate shared resources to unified workspace.

        Args:
            dry_run: If True, only simulate migration

        Returns:
            True if successful
        """
        if not self.legacy_shared_dir.exists():
            logger.info("No legacy shared/ directory found")
            return True

        target_shared = self.workspace_manager.shared_dir

        if dry_run:
            logger.info(f"[DRY RUN] Would migrate {self.legacy_shared_dir} -> {target_shared}")
            return True

        try:
            # Copy shared resources
            if target_shared.exists():
                logger.warning(f"Target shared directory already exists: {target_shared}")
            else:
                shutil.copytree(self.legacy_shared_dir, target_shared)
                logger.info(f"Migrated shared resources to {target_shared}")

            return True
        except Exception as e:
            logger.error(f"Failed to migrate shared resources: {e}")
            return False

    def _create_backup(self, path: Path, session_id: str) -> Path:
        """Create a backup of a session directory.

        Args:
            path: Path to backup
            session_id: Session identifier

        Returns:
            Path to backup file
        """
        backup_dir = self.project_root / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"{session_id}_backup_{timestamp}.tar.gz"

        with tarfile.open(backup_file, "w:gz") as tar:
            tar.add(path, arcname=session_id)

        logger.info(f"Created backup: {backup_file}")
        return backup_file

    def rollback_migration(self, session_id: str) -> bool:
        """Rollback a migrated session.

        Removes the session from unified workspace. Does NOT restore from backup.

        Args:
            session_id: Session ID to rollback

        Returns:
            True if successful
        """
        try:
            session = self.workspace_manager.get_session(session_id)
            session_dir = session.session_dir

            if session_dir.exists():
                shutil.rmtree(session_dir)
                logger.info(f"Rolled back session {session_id}")
                return True
            else:
                logger.warning(f"Session directory not found: {session_dir}")
                return False

        except Exception as e:
            logger.error(f"Failed to rollback session {session_id}: {e}")
            return False

    def cleanup_legacy_structure(
        self,
        remove_coordinator: bool = False,
        remove_subagents: bool = False,
        remove_shared: bool = False,
    ) -> dict[str, bool]:
        """Clean up legacy directory structure after successful migration.

        WARNING: This permanently removes legacy directories. Ensure backups exist.

        Args:
            remove_coordinator: Remove coordinator/ directory
            remove_subagents: Remove subagents/ directory
            remove_shared: Remove shared/ directory

        Returns:
            Dictionary of cleanup results
        """
        results = {}

        if remove_coordinator and self.legacy_coordinator_dir.exists():
            try:
                shutil.rmtree(self.legacy_coordinator_dir)
                results["coordinator"] = True
                logger.info("Removed legacy coordinator/ directory")
            except Exception as e:
                results["coordinator"] = False
                logger.error(f"Failed to remove coordinator/: {e}")

        if remove_subagents and self.legacy_subagents_dir.exists():
            try:
                shutil.rmtree(self.legacy_subagents_dir)
                results["subagents"] = True
                logger.info("Removed legacy subagents/ directory")
            except Exception as e:
                results["subagents"] = False
                logger.error(f"Failed to remove subagents/: {e}")

        if remove_shared and self.legacy_shared_dir.exists():
            try:
                shutil.rmtree(self.legacy_shared_dir)
                results["shared"] = True
                logger.info("Removed legacy shared/ directory")
            except Exception as e:
                results["shared"] = False
                logger.error(f"Failed to remove shared/: {e}")

        return results

    def get_migration_summary(self) -> dict[str, Any]:
        """Get summary of migration status.

        Returns:
            Dictionary with migration status information
        """
        legacy_sessions = self.detect_legacy_sessions()
        legacy_subagents = self.detect_legacy_subagents()
        migrated_sessions = self.workspace_manager.list_sessions()

        return {
            "legacy_sessions_count": len(legacy_sessions),
            "legacy_sessions": legacy_sessions,
            "legacy_subagents_count": len(legacy_subagents),
            "legacy_subagents": legacy_subagents,
            "migrated_sessions_count": len(migrated_sessions),
            "migrated_sessions": migrated_sessions,
            "workspace_root": str(self.workspace_manager.workspace_root),
        }
