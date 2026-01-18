"""Unit tests for OrchestratorAgent

Tests the orchestrator agent implementation with HierarchyManager integration.
"""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from regreader.orchestration.hierarchy_manager import HierarchyManager
from regreader.agents.orchestrated.base import OrchestratorAgent
from regreader.subagents.config import SubagentType


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def hierarchy_manager(temp_workspace):
    """Create a HierarchyManager instance for testing"""
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    return HierarchyManager(
        session_id=session_id,
        workspace_root=temp_workspace
    )


@pytest.fixture
def orchestrator_agent(hierarchy_manager):
    """Create an OrchestratorAgent instance for testing"""
    return OrchestratorAgent(
        reg_id="test_reg",
        hierarchy_manager=hierarchy_manager,
        model="test-model",
        api_key="test-key"
    )


class TestOrchestratorAgentInitialization:
    """Test OrchestratorAgent initialization"""

    def test_basic_initialization(self, orchestrator_agent, hierarchy_manager):
        """Test basic initialization"""
        assert orchestrator_agent.reg_id == "test_reg"
        assert orchestrator_agent.hierarchy_manager == hierarchy_manager
        assert orchestrator_agent.model == "test-model"
        assert orchestrator_agent.agent_id is not None
        assert orchestrator_agent.agent_id.startswith("orchestrator_")

    def test_initialization_without_hierarchy_manager(self, temp_workspace):
        """Test initialization without HierarchyManager"""
        agent = OrchestratorAgent(
            reg_id="test_reg",
            model="test-model",
            api_key="test-key"
        )
        assert agent.hierarchy_manager is None

    def test_agent_id_generation(self, hierarchy_manager):
        """Test that each agent gets unique ID"""
        agent1 = OrchestratorAgent(
            reg_id="test_reg",
            hierarchy_manager=hierarchy_manager,
            model="test-model",
            api_key="test-key"
        )
        agent2 = OrchestratorAgent(
            reg_id="test_reg",
            hierarchy_manager=hierarchy_manager,
            model="test-model",
            api_key="test-key"
        )
        assert agent1.agent_id != agent2.agent_id


class TestOrchestratorAgentRegistration:
    """Test agent registration with HierarchyManager"""

    @pytest.mark.asyncio
    async def test_ensure_initialized_registers_agent(self, orchestrator_agent):
        """Test that _ensure_initialized registers agent"""
        query = "Test query"
        await orchestrator_agent._ensure_initialized(query)

        # Check agent is registered in hierarchy
        stack = orchestrator_agent.hierarchy_manager.get_call_stack()
        assert len(stack) == 1
        assert stack[0]["agent_id"] == orchestrator_agent.agent_id
        assert stack[0]["agent_name"] == "OrchestratorAgent"
        assert stack[0]["level"] == 2
        assert stack[0]["user_input"] == query

    @pytest.mark.asyncio
    async def test_ensure_initialized_idempotent(self, orchestrator_agent):
        """Test that _ensure_initialized can be called multiple times"""
        query = "Test query"
        await orchestrator_agent._ensure_initialized(query)
        await orchestrator_agent._ensure_initialized(query)

        # Should still have only one agent in stack
        stack = orchestrator_agent.hierarchy_manager.get_call_stack()
        assert len(stack) == 1


class TestTaskPlanning:
    """Test task planning functionality"""

    @pytest.mark.asyncio
    async def test_plan_subtasks_search_query(self, orchestrator_agent):
        """Test planning for search-related query"""
        query = "母线失压如何处理？"
        subtasks = await orchestrator_agent._plan_subtasks(query)

        assert len(subtasks) > 0
        assert any(task["task_type"] == SubagentType.SEARCH for task in subtasks)

    @pytest.mark.asyncio
    async def test_plan_subtasks_table_query(self, orchestrator_agent):
        """Test planning for table-related query"""
        query = "查找相关表格数据"
        subtasks = await orchestrator_agent._plan_subtasks(query)

        assert len(subtasks) > 0
        assert any(task["task_type"] == SubagentType.TABLE for task in subtasks)

    @pytest.mark.asyncio
    async def test_plan_subtasks_reference_query(self, orchestrator_agent):
        """Test planning for reference-related query"""
        query = "解析交叉引用"
        subtasks = await orchestrator_agent._plan_subtasks(query)

        assert len(subtasks) > 0
        assert any(task["task_type"] == SubagentType.REFERENCE for task in subtasks)

    @pytest.mark.asyncio
    async def test_plan_subtasks_complex_query(self, orchestrator_agent):
        """Test planning for complex query requiring multiple subagents"""
        query = "母线失压如何处理？需要查看相关表格和注释"
        subtasks = await orchestrator_agent._plan_subtasks(query)

        # Should plan multiple subtasks
        assert len(subtasks) >= 2
        task_types = [task["task_type"] for task in subtasks]
        assert SubagentType.SEARCH in task_types or SubagentType.TABLE in task_types


class TestSubtaskExecution:
    """Test subtask execution functionality"""

    @pytest.mark.asyncio
    async def test_execute_subtask_returns_result(self, orchestrator_agent):
        """Test that subtask execution returns a result"""
        subtask = {
            "task_type": SubagentType.SEARCH,
            "description": "Search for content"
        }

        result = await orchestrator_agent._execute_subtask(subtask)

        assert result is not None
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_execute_subtask_different_types(self, orchestrator_agent):
        """Test executing different subtask types"""
        subtask_types = [
            SubagentType.SEARCH,
            SubagentType.TABLE,
            SubagentType.REFERENCE
        ]

        for task_type in subtask_types:
            subtask = {
                "task_type": task_type,
                "description": f"Test {task_type.value} task"
            }
            result = await orchestrator_agent._execute_subtask(subtask)
            assert result is not None


class TestResultAggregation:
    """Test result aggregation functionality"""

    @pytest.mark.asyncio
    async def test_aggregate_results_single(self, orchestrator_agent):
        """Test aggregating single result"""
        results = ["Result 1"]
        aggregated = await orchestrator_agent._aggregate_results(results)

        assert aggregated is not None
        assert isinstance(aggregated, str)
        assert "Result 1" in aggregated

    @pytest.mark.asyncio
    async def test_aggregate_results_multiple(self, orchestrator_agent):
        """Test aggregating multiple results"""
        results = ["Result 1", "Result 2", "Result 3"]
        aggregated = await orchestrator_agent._aggregate_results(results)

        assert aggregated is not None
        assert isinstance(aggregated, str)

    @pytest.mark.asyncio
    async def test_aggregate_results_empty(self, orchestrator_agent):
        """Test aggregating empty results"""
        results = []
        aggregated = await orchestrator_agent._aggregate_results(results)

        assert aggregated is not None
        assert isinstance(aggregated, str)
