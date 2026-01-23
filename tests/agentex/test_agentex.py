"""AgentEx 单元测试

测试 agentex 模块的核心功能。
"""

import pytest
import asyncio
from typing import Any

# 导入测试目标
from regreader.agentex import (
    # Types
    AgentResponse,
    ToolResult,
    AgentEvent,
    LLMConfig,
    # Exceptions
    AgentExError,
    AgentError,
    ToolError,
    # Agent
    BaseAgent,
    AgentState,
    # Config
    AgentConfig,
    ClaudeConfig,
    PydanticConfig,
    LangGraphConfig,
    # Tools
    Tool,
    FunctionTool,
    ToolRegistry,
    ToolExecutor,
    # Shared
    StatusCallback,
    NullCallback,
    EventType,
    Event,
    AgentMemory,
    MemoryStore,
    # Frameworks
    FrameworkType,
    FrameworkFactory,
    # Orchestration
    ParallelExecutor,
    TaskPool,
    ExecutionResult,
    # MCP
    MCPToolAdapter,
    MCPToolRegistry,
)


class TestTypes:
    """测试类型定义"""

    def test_agent_response(self):
        """测试 AgentResponse 数据类"""
        response = AgentResponse(content="Hello")
        assert response.content == "Hello"
        assert response.sources == []
        assert response.tool_calls == []
        assert response.metadata == {}

    def test_tool_result(self):
        """测试 ToolResult 数据类"""
        result = ToolResult(name="test_tool", output={"key": "value"})
        assert result.name == "test_tool"
        assert result.output == {"key": "value"}
        assert result.success is True
        assert result.error is None

    def test_agent_event(self):
        """测试 AgentEvent 数据类"""
        event = AgentEvent(event_type="thinking_start", data={"message": "test"})
        assert event.event_type == "thinking_start"
        assert event.data == {"message": "test"}
        assert event.timestamp > 0

    def test_llm_config_defaults(self):
        """测试 LLMConfig 默认值"""
        config = LLMConfig()
        assert config.temperature == 0.0
        assert config.max_tokens is None


class TestAgentState:
    """测试 AgentState"""

    def test_add_message(self):
        """测试添加消息"""
        state = AgentState(max_history=5)
        state.add_message("user", "Hello")
        state.add_message("assistant", "Hi there!")

        history = state.get_history()
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello"

    def test_max_history_limit(self):
        """测试历史消息限制"""
        state = AgentState(max_history=3)
        for i in range(5):
            state.add_message("user", f"Message {i}")

        history = state.get_history()
        assert len(history) == 3
        assert history[0]["content"] == "Message 2"

    def test_clear(self):
        """测试清空状态"""
        state = AgentState()
        state.add_message("user", "Hello")
        state.clear()
        assert len(state) == 0


class TestAgentConfig:
    """测试配置类"""

    def test_agent_config_defaults(self):
        """测试 AgentConfig 默认值"""
        config = AgentConfig()
        assert config.name == "agent"
        assert config.memory_enabled is True
        assert config.max_history == 50
        assert config.max_iterations == 10

    def test_claude_config(self):
        """测试 ClaudeConfig"""
        config = ClaudeConfig(name="test-claude", model="claude-3-opus")
        assert config.name == "test-claude"
        assert config.model == "claude-3-opus"
        assert config.llm is not None
        assert config.llm.model == "claude-3-opus"

    def test_pydantic_config(self):
        """测试 PydanticConfig"""
        config = PydanticConfig(name="test-pydantic", model="gpt-4")
        assert config.name == "test-pydantic"
        assert config.model == "gpt-4"

    def test_langgraph_config(self):
        """测试 LangGraphConfig"""
        config = LangGraphConfig(name="test-langgraph")
        assert config.name == "test-langgraph"
        assert config.state_schema is None
        assert config.checkpointer is None


class TestToolSystem:
    """测试工具系统"""

    def test_function_tool(self):
        """测试 FunctionTool"""

        async def my_func(context, **kwargs):
            return f"Result: {kwargs.get('input', 'none')}"

        tool = FunctionTool(
            name="my_tool",
            description="A test tool",
            func=my_func,
            parameters={"type": "object", "properties": {"input": {"type": "string"}}},
        )

        assert tool.name == "my_tool"
        assert tool.description == "A test tool"
        assert "input" in tool.parameters["properties"]

    def test_tool_registry(self):
        """测试 ToolRegistry"""
        registry = ToolRegistry()

        async def dummy_func(context, **kwargs):
            return "ok"

        tool = FunctionTool(name="dummy", description="Dummy tool", func=dummy_func)
        registry.register(tool)

        assert "dummy" in registry
        assert len(registry) == 1
        assert registry.get("dummy") is tool

        registry.unregister("dummy")
        assert "dummy" not in registry

    def test_tool_registry_schema_generation(self):
        """测试工具 schema 生成"""
        registry = ToolRegistry()

        async def func1(context, **kwargs):
            return "1"

        async def func2(context, **kwargs):
            return "2"

        registry.register(FunctionTool(name="tool1", description="Tool 1", func=func1))
        registry.register(FunctionTool(name="tool2", description="Tool 2", func=func2))

        schema = registry.generate_schema()
        assert len(schema) == 2
        assert schema[0]["type"] == "function"
        assert schema[0]["function"]["name"] == "tool1"

    @pytest.mark.asyncio
    async def test_tool_executor(self):
        """测试 ToolExecutor"""

        async def add_func(context, a: int = 0, b: int = 0, **kwargs):
            return a + b

        tool = FunctionTool(name="add", description="Add two numbers", func=add_func)
        executor = ToolExecutor()
        executor.add_tool(tool)

        result = await executor.execute("add", {}, a=2, b=3)
        assert result == 5


class TestMemory:
    """测试记忆系统"""

    def test_agent_memory(self):
        """测试 AgentMemory"""
        memory = AgentMemory(max_items=10)
        memory.add("user", "Hello")
        memory.add("assistant", "Hi!")

        assert len(memory) == 2
        assert bool(memory) is True

        messages = memory.get_messages()
        assert len(messages) == 2
        assert messages[0]["role"] == "user"

    def test_memory_context(self):
        """测试记忆上下文生成"""
        memory = AgentMemory()
        memory.add("user", "What is Python?")
        memory.add("assistant", "Python is a programming language.")

        context = memory.get_context()
        assert "对话历史" in context
        assert "user" in context

    def test_memory_store(self):
        """测试 MemoryStore"""
        store = MemoryStore()
        memory = AgentMemory()
        memory.add("user", "Test")

        store.save("session1", memory)
        loaded = store.load("session1")

        assert loaded is not None
        assert len(loaded) == 1

        store.delete("session1")
        assert store.load("session1") is None


class TestEvents:
    """测试事件系统"""

    def test_event_types(self):
        """测试事件类型枚举"""
        assert EventType.THINKING_START.name == "THINKING_START"
        assert EventType.TOOL_CALL_START.name == "TOOL_CALL_START"
        assert EventType.TEXT_DELTA.name == "TEXT_DELTA"

    def test_event_creation(self):
        """测试事件创建"""
        event = Event(type=EventType.THINKING_START)
        assert event.type == EventType.THINKING_START
        assert event.timestamp is not None

    def test_event_with_data(self):
        """测试带数据的事件"""
        event = Event(type=EventType.TEXT_DELTA, data={"text": "Hello"})
        assert event.data["text"] == "Hello"


class TestCallbacks:
    """测试回调系统"""

    @pytest.mark.asyncio
    async def test_null_callback(self):
        """测试空回调"""
        callback = NullCallback()
        event = AgentEvent(event_type="test", data={})
        # 应该不抛出异常
        await callback.on_event(event)


class TestFrameworkFactory:
    """测试框架工厂"""

    def test_framework_types(self):
        """测试框架类型枚举"""
        assert FrameworkType.CLAUDE.value == "claude"
        assert FrameworkType.PYDANTIC.value == "pydantic"
        assert FrameworkType.LANGGRAPH.value == "langgraph"

    def test_factory_registration(self):
        """测试工厂注册"""
        available = FrameworkFactory.list_available()
        assert FrameworkType.CLAUDE in available
        assert FrameworkType.PYDANTIC in available
        assert FrameworkType.LANGGRAPH in available

    def test_factory_is_available(self):
        """测试框架可用性检查"""
        assert FrameworkFactory.is_available(FrameworkType.CLAUDE) is True
        assert FrameworkFactory.is_available(FrameworkType.PYDANTIC) is True


class TestParallelExecutor:
    """测试并行执行器"""

    @pytest.mark.asyncio
    async def test_sequential_execution(self):
        """测试顺序执行"""
        executor = ParallelExecutor(mode="sequential")
        results_order = []

        async def task1():
            results_order.append(1)
            return "task1"

        async def task2():
            results_order.append(2)
            return "task2"

        tasks = [("t1", task1), ("t2", task2)]
        results = await executor.execute(tasks)

        assert len(results) == 2
        assert results[0].task_id == "t1"
        assert results[0].result == "task1"
        assert results_order == [1, 2]

    @pytest.mark.asyncio
    async def test_parallel_execution(self):
        """测试并行执行"""
        executor = ParallelExecutor(mode="parallel")

        async def task1():
            await asyncio.sleep(0.01)
            return "task1"

        async def task2():
            return "task2"

        tasks = [("t1", task1), ("t2", task2)]
        results = await executor.execute(tasks)

        assert len(results) == 2
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_execution_with_failure(self):
        """测试执行失败处理"""
        executor = ParallelExecutor(mode="sequential", fail_strategy="continue")

        async def failing_task():
            raise ValueError("Test error")

        async def success_task():
            return "success"

        tasks = [("fail", failing_task), ("success", success_task)]
        results = await executor.execute(tasks)

        assert len(results) == 2
        assert results[0].success is False
        assert "Test error" in results[0].error
        assert results[1].success is True


class TestTaskPool:
    """测试任务池"""

    @pytest.mark.asyncio
    async def test_task_pool_map(self):
        """测试任务池映射"""
        pool = TaskPool(max_concurrent=2)

        async def double(x):
            return x * 2

        results = await pool.map(double, [1, 2, 3, 4])
        assert results == [2, 4, 6, 8]

    @pytest.mark.asyncio
    async def test_task_pool_submit(self):
        """测试任务提交"""
        pool = TaskPool(max_concurrent=5)

        async def compute():
            return 42

        result = await pool.submit(compute())
        assert result == 42


class TestMCPAdapter:
    """测试 MCP 适配器"""

    def test_mcp_tool_adapter_properties(self):
        """测试 MCPToolAdapter 属性"""

        class MockMCPClient:
            async def call_tool(self, name, args):
                return {"result": "ok"}

        adapter = MCPToolAdapter(
            tool_name="test_mcp_tool",
            tool_description="A test MCP tool",
            tool_parameters={"type": "object", "properties": {}},
            mcp_client=MockMCPClient(),
        )

        assert adapter.name == "test_mcp_tool"
        assert adapter.description == "A test MCP tool"
        assert adapter.parameters == {"type": "object", "properties": {}}

    @pytest.mark.asyncio
    async def test_mcp_tool_adapter_execution(self):
        """测试 MCPToolAdapter 执行"""

        class MockMCPClient:
            async def call_tool(self, name, args):
                return {"result": f"Called {name} with {args}"}

        adapter = MCPToolAdapter(
            tool_name="echo",
            tool_description="Echo tool",
            tool_parameters={},
            mcp_client=MockMCPClient(),
        )

        result = await adapter._run({}, message="hello")
        assert "Called echo" in str(result)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
