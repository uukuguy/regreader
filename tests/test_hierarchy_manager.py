"""Unit tests for HierarchyManager

Tests the agent call stack management, shared context, and state persistence.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from regreader.orchestration.hierarchy_manager import HierarchyManager


@pytest.fixture
def temp_session_dir():
    """Create a temporary session directory for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def hierarchy_manager(temp_session_dir):
    """Create a HierarchyManager instance for testing"""
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    return HierarchyManager(
        session_id=session_id,
        workspace_root=temp_session_dir
    )


class TestHierarchyManagerBasics:
    """Test basic HierarchyManager functionality"""

    def test_initialization(self, hierarchy_manager, temp_session_dir):
        """Test HierarchyManager initialization"""
        assert hierarchy_manager.session_id is not None
        assert hierarchy_manager.workspace_root == temp_session_dir
        assert hierarchy_manager.session_dir.exists()
        assert hierarchy_manager.get_call_stack() == []

    def test_session_directory_creation(self, hierarchy_manager):
        """Test that session directory is created"""
        assert hierarchy_manager.session_dir.exists()
        assert hierarchy_manager.session_dir.is_dir()


class TestAgentStackManagement:
    """Test agent stack push/pop operations"""

    def test_push_agent_root(self, hierarchy_manager):
        """Test pushing root agent (no parent)"""
        hierarchy_manager.push_agent(
            agent_id="orch_001",
            agent_name="OrchestratorAgent",
            parent_id=None,
            level=2,
            user_input="Test query"
        )

        stack = hierarchy_manager.get_call_stack()
        assert len(stack) == 1
        assert stack[0]["agent_id"] == "orch_001"
        assert stack[0]["agent_name"] == "OrchestratorAgent"
        assert stack[0]["parent_id"] is None
        assert stack[0]["level"] == 2
        assert stack[0]["user_input"] == "Test query"
        assert stack[0]["status"] == "running"

    def test_push_agent_with_parent(self, hierarchy_manager):
        """Test pushing child agent"""
        # Push parent
        hierarchy_manager.push_agent(
            agent_id="orch_001",
            agent_name="OrchestratorAgent",
            parent_id=None,
            level=2,
            user_input="Test query"
        )

        # Push child
        hierarchy_manager.push_agent(
            agent_id="search_001",
            agent_name="SearchAgent",
            parent_id="orch_001",
            level=1,
            user_input="Search subtask"
        )

        stack = hierarchy_manager.get_call_stack()
        assert len(stack) == 2
        assert stack[1]["agent_id"] == "search_001"
        assert stack[1]["parent_id"] == "orch_001"
        assert stack[1]["level"] == 1

    def test_pop_agent(self, hierarchy_manager):
        """Test popping agent from stack"""
        # Push two agents
        hierarchy_manager.push_agent(
            agent_id="orch_001",
            agent_name="OrchestratorAgent",
            parent_id=None,
            level=2,
            user_input="Test query"
        )
        hierarchy_manager.push_agent(
            agent_id="search_001",
            agent_name="SearchAgent",
            parent_id="orch_001",
            level=1,
            user_input="Search subtask"
        )

        # Pop child agent
        hierarchy_manager.pop_agent("search_001")
        stack = hierarchy_manager.get_call_stack()
        assert len(stack) == 1
        assert stack[0]["agent_id"] == "orch_001"

    def test_pop_nonexistent_agent(self, hierarchy_manager):
        """Test popping agent that doesn't exist"""
        hierarchy_manager.push_agent(
            agent_id="orch_001",
            agent_name="OrchestratorAgent",
            parent_id=None,
            level=2,
            user_input="Test query"
        )

        # Should not raise error, just log warning
        hierarchy_manager.pop_agent("nonexistent_001")
        stack = hierarchy_manager.get_call_stack()
        assert len(stack) == 1  # Original agent still there


class TestAgentStatusUpdates:
    """Test agent status update operations"""

    def test_update_agent_status(self, hierarchy_manager):
        """Test updating agent status"""
        hierarchy_manager.push_agent(
            agent_id="orch_001",
            agent_name="OrchestratorAgent",
            parent_id=None,
            level=2,
            user_input="Test query"
        )

        hierarchy_manager.update_agent_status(
            agent_id="orch_001",
            status="completed",
            thinking="Analysis complete",
            output="Final result"
        )

        stack = hierarchy_manager.get_call_stack()
        agent = stack[0]
        assert agent["status"] == "completed"
        assert agent["thinking"] == "Analysis complete"
        assert agent["output"] == "Final result"

    def test_update_nonexistent_agent_status(self, hierarchy_manager):
        """Test updating status of nonexistent agent"""
        # Should not raise error, just log warning
        hierarchy_manager.update_agent_status(
            agent_id="nonexistent_001",
            status="completed"
        )

    def test_partial_status_update(self, hierarchy_manager):
        """Test updating only some fields"""
        hierarchy_manager.push_agent(
            agent_id="orch_001",
            agent_name="OrchestratorAgent",
            parent_id=None,
            level=2,
            user_input="Test query"
        )

        # Update only thinking
        hierarchy_manager.update_agent_status(
            agent_id="orch_001",
            status="running",
            thinking="Processing..."
        )

        stack = hierarchy_manager.get_call_stack()
        agent = stack[0]
        assert agent["status"] == "running"
        assert agent["thinking"] == "Processing..."
        assert agent.get("output") is None


class TestAgentContext:
    """Test agent context retrieval"""

    def test_get_agent_context(self, hierarchy_manager):
        """Test getting context for specific agent"""
        hierarchy_manager.push_agent(
            agent_id="orch_001",
            agent_name="OrchestratorAgent",
            parent_id=None,
            level=2,
            user_input="Test query"
        )

        context = hierarchy_manager.get_agent_context("orch_001")
        assert context is not None
        assert context["agent_id"] == "orch_001"
        assert context["agent_name"] == "OrchestratorAgent"
        assert context["user_input"] == "Test query"

    def test_get_nonexistent_agent_context(self, hierarchy_manager):
        """Test getting context for nonexistent agent"""
        context = hierarchy_manager.get_agent_context("nonexistent_001")
        assert context is None


class TestStatePersistence:
    """Test state save/load operations"""

    def test_save_state(self, hierarchy_manager):
        """Test saving state to files"""
        # Push some agents
        hierarchy_manager.push_agent(
            agent_id="orch_001",
            agent_name="OrchestratorAgent",
            parent_id=None,
            level=2,
            user_input="Test query"
        )
        hierarchy_manager.push_agent(
            agent_id="search_001",
            agent_name="SearchAgent",
            parent_id="orch_001",
            level=1,
            user_input="Search subtask"
        )

        # Save state
        hierarchy_manager.save_state()

        # Check files exist
        call_stack_file = hierarchy_manager.session_dir / "call_stack.json"
        shared_context_file = hierarchy_manager.session_dir / "shared_context.json"

        assert call_stack_file.exists()
        assert shared_context_file.exists()

        # Verify content
        with open(call_stack_file, "r", encoding="utf-8") as f:
            saved_stack = json.load(f)
        assert len(saved_stack) == 2
        assert saved_stack[0]["agent_id"] == "orch_001"
        assert saved_stack[1]["agent_id"] == "search_001"

    def test_load_state(self, hierarchy_manager, temp_session_dir):
        """Test loading state from files"""
        # Create initial state
        hierarchy_manager.push_agent(
            agent_id="orch_001",
            agent_name="OrchestratorAgent",
            parent_id=None,
            level=2,
            user_input="Test query"
        )
        hierarchy_manager.save_state()

        # Create new manager and load state
        new_manager = HierarchyManager(
            session_id=hierarchy_manager.session_id,
            workspace_root=temp_session_dir
        )
        new_manager.load_state(hierarchy_manager.session_id)

        # Verify loaded state
        stack = new_manager.get_call_stack()
        assert len(stack) == 1
        assert stack[0]["agent_id"] == "orch_001"

    def test_load_nonexistent_state(self, hierarchy_manager):
        """Test loading state that doesn't exist"""
        # Should not raise error, just log warning
        hierarchy_manager.load_state("nonexistent_session")
        assert hierarchy_manager.get_call_stack() == []


class TestComplexScenarios:
    """Test complex multi-agent scenarios"""

    def test_nested_agent_hierarchy(self, hierarchy_manager):
        """Test deeply nested agent hierarchy"""
        # L2: Orchestrator
        hierarchy_manager.push_agent(
            agent_id="orch_001",
            agent_name="OrchestratorAgent",
            parent_id=None,
            level=2,
            user_input="Complex query"
        )

        # L1: Search agent
        hierarchy_manager.push_agent(
            agent_id="search_001",
            agent_name="SearchAgent",
            parent_id="orch_001",
            level=1,
            user_input="Search subtask"
        )

        # L1: Table agent
        hierarchy_manager.push_agent(
            agent_id="table_001",
            agent_name="TableAgent",
            parent_id="orch_001",
            level=1,
            user_input="Table subtask"
        )

        stack = hierarchy_manager.get_call_stack()
        assert len(stack) == 3
        assert stack[0]["level"] == 2
        assert stack[1]["level"] == 1
        assert stack[2]["level"] == 1
        assert stack[1]["parent_id"] == "orch_001"
        assert stack[2]["parent_id"] == "orch_001"

    def test_sequential_agent_execution(self, hierarchy_manager):
        """Test sequential execution of multiple agents"""
        # Push orchestrator
        hierarchy_manager.push_agent(
            agent_id="orch_001",
            agent_name="OrchestratorAgent",
            parent_id=None,
            level=2,
            user_input="Test query"
        )

        # Execute first subagent
        hierarchy_manager.push_agent(
            agent_id="search_001",
            agent_name="SearchAgent",
            parent_id="orch_001",
            level=1,
            user_input="Search subtask"
        )
        hierarchy_manager.update_agent_status(
            agent_id="search_001",
            status="completed",
            output="Search results"
        )
        hierarchy_manager.pop_agent("search_001")

        # Execute second subagent
        hierarchy_manager.push_agent(
            agent_id="table_001",
            agent_name="TableAgent",
            parent_id="orch_001",
            level=1,
            user_input="Table subtask"
        )
        hierarchy_manager.update_agent_status(
            agent_id="table_001",
            status="completed",
            output="Table results"
        )
        hierarchy_manager.pop_agent("table_001")

        # Only orchestrator should remain
        stack = hierarchy_manager.get_call_stack()
        assert len(stack) == 1
        assert stack[0]["agent_id"] == "orch_001"

    def test_state_persistence_across_sessions(self, hierarchy_manager, temp_session_dir):
        """Test state persistence and recovery"""
        # Session 1: Create and save state
        hierarchy_manager.push_agent(
            agent_id="orch_001",
            agent_name="OrchestratorAgent",
            parent_id=None,
            level=2,
            user_input="Test query"
        )
        hierarchy_manager.update_agent_status(
            agent_id="orch_001",
            status="running",
            thinking="Processing query..."
        )
        hierarchy_manager.save_state()
        session_id = hierarchy_manager.session_id

        # Session 2: Load and continue
        new_manager = HierarchyManager(
            session_id=session_id,
            workspace_root=temp_session_dir
        )
        new_manager.load_state(session_id)

        # Verify state was restored
        stack = new_manager.get_call_stack()
        assert len(stack) == 1
        assert stack[0]["agent_id"] == "orch_001"
        assert stack[0]["status"] == "running"
        assert stack[0]["thinking"] == "Processing query..."

        # Continue execution
        new_manager.update_agent_status(
            agent_id="orch_001",
            status="completed",
            output="Final result"
        )
        new_manager.save_state()

        # Verify updated state
        stack = new_manager.get_call_stack()
        assert stack[0]["status"] == "completed"
        assert stack[0]["output"] == "Final result"
