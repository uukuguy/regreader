"""
HierarchyManager - Agent call stack and shared context management.

Inspired by infiAgent's hierarchical orchestration patterns.
Manages agent call stack, shared context, and parent-child relationships.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

from loguru import logger

from regreader.core.config import get_settings

if TYPE_CHECKING:
    from regreader.workspace import WorkspaceManager, SessionWorkspace


class HierarchyManager:
    """
    Manages agent call stack and shared context for hierarchical multi-agent orchestration.

    Features:
    - Stack-based agent call tracking
    - Parent-child relationship management
    - Shared context structure for agent communication
    - JSON-based state persistence

    Inspired by infiAgent's HierarchyManager.
    """

    def __init__(
        self,
        session_id: str | None = None,
        workspace_manager: "WorkspaceManager | None" = None,
    ):
        """
        Initialize HierarchyManager.

        Args:
            session_id: Optional session ID. If not provided, generates a new one.
            workspace_manager: Optional WorkspaceManager instance. If not provided, creates one.
        """
        self.config = get_settings()

        # Initialize or use provided workspace manager
        if workspace_manager is None:
            from regreader.workspace import WorkspaceManager
            workspace_manager = WorkspaceManager(self.config.workspace_root)

        self.workspace_manager = workspace_manager

        # Create or get session workspace
        if session_id:
            try:
                self.session_workspace = self.workspace_manager.get_session(session_id)
            except FileNotFoundError:
                # Session doesn't exist, create it
                self.session_workspace = self.workspace_manager.create_session(session_id)
        else:
            # Create new session with auto-generated ID
            self.session_workspace = self.workspace_manager.create_session()

        self.session_id = self.session_workspace.session_id
        self.session_dir = self.session_workspace.coordinator_dir

        # Initialize state
        self.call_stack: list[dict[str, Any]] = []
        self.shared_context: dict[str, Any] = {
            "session_id": self.session_id,
            "agents_status": {},
            "hierarchy": {},
            "current_instruction": None,
        }

        # Ensure session directory exists
        self.session_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"HierarchyManager initialized for session: {self.session_id}")

    def _generate_session_id(self) -> str:
        """Generate a unique session ID.

        Note: This method is kept for backward compatibility but is no longer
        used in the main initialization flow. Session IDs are now generated
        by WorkspaceManager.create_session().
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"session_{timestamp}"

    def _get_session_dir(self) -> Path:
        """Get session directory path.

        Note: This method is kept for backward compatibility. New code should
        use self.session_workspace.coordinator_dir directly.
        """
        return self.session_workspace.coordinator_dir

    def push_agent(
        self,
        agent_id: str,
        agent_name: str,
        parent_id: str | None,
        level: int,
        user_input: str,
    ) -> None:
        """
        Push an agent onto the call stack.

        Args:
            agent_id: Unique agent identifier
            agent_name: Agent name (e.g., "OrchestratorAgent", "LocateChaptersSubagent")
            parent_id: Parent agent ID (None for root agent)
            level: Agent level (2=Orchestrator, 1=Subagent, 0=Tool)
            user_input: Input/task for this agent
        """
        agent_entry = {
            "agent_id": agent_id,
            "agent_name": agent_name,
            "parent_id": parent_id,
            "level": level,
            "user_input": user_input,
            "start_time": datetime.now().isoformat(),
        }

        self.call_stack.append(agent_entry)

        # Update shared context
        self.shared_context["agents_status"][agent_id] = {
            "agent_name": agent_name,
            "status": "running",
            "initial_input": user_input,
            "start_time": agent_entry["start_time"],
            "latest_thinking": None,
            "final_output": None,
        }

        # Update hierarchy
        self.shared_context["hierarchy"][agent_id] = {
            "parent": parent_id,
            "children": [],
            "level": level,
        }

        # Add to parent's children list
        if parent_id and parent_id in self.shared_context["hierarchy"]:
            self.shared_context["hierarchy"][parent_id]["children"].append(agent_id)

        self.save_state()
        logger.debug(f"Pushed agent {agent_name} (ID: {agent_id}) to stack")

    def pop_agent(self, agent_id: str) -> None:
        """
        Pop an agent from the call stack.

        Args:
            agent_id: Agent identifier to remove
        """
        # Remove from call stack
        self.call_stack = [entry for entry in self.call_stack if entry["agent_id"] != agent_id]

        # Update status to completed
        if agent_id in self.shared_context["agents_status"]:
            self.shared_context["agents_status"][agent_id]["status"] = "completed"
            self.shared_context["agents_status"][agent_id]["end_time"] = datetime.now().isoformat()

        self.save_state()
        logger.debug(f"Popped agent {agent_id} from stack")

    def update_agent_status(
        self,
        agent_id: str,
        status: str,
        thinking: str | None = None,
        output: str | None = None,
    ) -> None:
        """
        Update agent status and thinking/output.

        Args:
            agent_id: Agent identifier
            status: Agent status (running/completed/failed)
            thinking: Latest thinking (optional)
            output: Final output (optional)
        """
        if agent_id not in self.shared_context["agents_status"]:
            logger.warning(f"Agent {agent_id} not found in shared context")
            return

        self.shared_context["agents_status"][agent_id]["status"] = status

        if thinking is not None:
            self.shared_context["agents_status"][agent_id]["latest_thinking"] = thinking

        if output is not None:
            self.shared_context["agents_status"][agent_id]["final_output"] = output

        self.save_state()
        logger.debug(f"Updated agent {agent_id} status to {status}")

    def get_agent_context(self, agent_id: str) -> dict[str, Any]:
        """
        Get context for a specific agent.

        Args:
            agent_id: Agent identifier

        Returns:
            Agent context including status, thinking, output, and hierarchy info
        """
        if agent_id not in self.shared_context["agents_status"]:
            return {}

        context = {
            "status": self.shared_context["agents_status"][agent_id],
            "hierarchy": self.shared_context["hierarchy"].get(agent_id, {}),
        }

        # Add parent context if exists
        parent_id = context["hierarchy"].get("parent")
        if parent_id and parent_id in self.shared_context["agents_status"]:
            context["parent_status"] = self.shared_context["agents_status"][parent_id]

        return context

    def get_call_stack(self) -> list[dict[str, Any]]:
        """
        Get current agent call stack.

        Returns:
            List of agent entries in the call stack
        """
        return self.call_stack.copy()

    def save_state(self) -> None:
        """Save current state to JSON files."""
        try:
            # Save call stack
            stack_file = self.session_dir / "call_stack.json"
            with open(stack_file, "w", encoding="utf-8") as f:
                json.dump({"stack": self.call_stack}, f, indent=2, ensure_ascii=False)

            # Save shared context
            context_file = self.session_dir / "shared_context.json"
            with open(context_file, "w", encoding="utf-8") as f:
                json.dump(self.shared_context, f, indent=2, ensure_ascii=False)

            logger.debug(f"State saved to {self.session_dir}")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def load_state(self, session_id: str) -> None:
        """
        Load state from a previous session.

        Args:
            session_id: Session ID to load
        """
        # Get session workspace
        try:
            self.session_workspace = self.workspace_manager.get_session(session_id)
        except FileNotFoundError:
            logger.error(f"Session {session_id} not found")
            raise

        self.session_id = self.session_workspace.session_id
        self.session_dir = self.session_workspace.coordinator_dir

        try:
            # Load call stack
            stack_file = self.session_dir / "call_stack.json"
            if stack_file.exists():
                with open(stack_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.call_stack = data.get("stack", [])

            # Load shared context
            context_file = self.session_dir / "shared_context.json"
            if context_file.exists():
                with open(context_file, "r", encoding="utf-8") as f:
                    self.shared_context = json.load(f)

            logger.info(f"State loaded from session: {session_id}")
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            raise
