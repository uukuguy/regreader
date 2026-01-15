"""测试 RegSearchSubagent"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from regreader.infrastructure.file_context import FileContext
from regreader.subagents.base import SubagentContext
from regreader.subagents.config import REGSEARCH_AGENT_CONFIG
from regreader.subagents.regsearch import RegSearchSubagent
from regreader.orchestration.result import SubagentResult


class TestRegSearchSubagent:
    """RegSearchSubagent 单元测试"""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as d:
            temp = Path(d)
            # 创建目录结构
            (temp / "subagents" / "regsearch" / "scratch").mkdir(parents=True)
            (temp / "subagents" / "regsearch" / "logs").mkdir(parents=True)
            (temp / "shared" / "data").mkdir(parents=True)
            (temp / "coordinator").mkdir()
            yield temp

    @pytest.fixture
    def mock_mcp_client(self) -> MagicMock:
        """创建模拟 MCP 客户端"""
        client = MagicMock()
        client.call_tool = AsyncMock(return_value={
            "results": [
                {"content": "测试内容", "source": "angui_2024 P10"}
            ]
        })
        return client

    def test_init_default_config(self) -> None:
        """测试使用默认配置初始化"""
        agent = RegSearchSubagent()
        assert agent.config == REGSEARCH_AGENT_CONFIG
        assert agent.name == "regsearch"
        assert agent.file_context is None

    def test_init_with_file_system(self, temp_dir: Path) -> None:
        """测试启用文件系统模式"""
        agent = RegSearchSubagent(
            use_file_system=True,
            project_root=temp_dir,
        )
        assert agent.uses_file_system is True
        assert agent.file_context is not None
        assert agent.file_context.subagent_name == "regsearch"

    def test_init_with_custom_file_context(self, temp_dir: Path) -> None:
        """测试使用自定义 FileContext"""
        file_context = FileContext(
            subagent_name="custom",
            base_dir=temp_dir / "subagents" / "regsearch",
            project_root=temp_dir,
        )
        agent = RegSearchSubagent(file_context=file_context)
        assert agent.file_context is file_context

    def test_tools_property(self) -> None:
        """测试工具列表属性"""
        agent = RegSearchSubagent()
        assert "list_regulations" in agent.tools
        assert "smart_search" in agent.tools
        assert "search_tables" in agent.tools
        assert len(agent.tools) > 10  # 至少 16 个工具

    @pytest.mark.asyncio
    async def test_execute_without_mcp(self) -> None:
        """测试没有 MCP 客户端的执行"""
        agent = RegSearchSubagent()
        context = SubagentContext(
            query="测试查询",
            reg_id="angui_2024",
        )
        result = await agent.execute(context)
        assert result.success is False
        assert "MCP 客户端未配置" in result.content

    @pytest.mark.asyncio
    async def test_execute_with_mcp(self, mock_mcp_client: MagicMock) -> None:
        """测试使用 MCP 客户端的执行"""
        agent = RegSearchSubagent(mcp_client=mock_mcp_client)
        context = SubagentContext(
            query="母线失压处理",
            reg_id="angui_2024",
        )
        result = await agent.execute(context)
        assert result.success is True
        assert len(result.sources) > 0
        # 验证调用了 MCP 工具
        assert mock_mcp_client.call_tool.called

    @pytest.mark.asyncio
    async def test_execute_with_file_system(
        self,
        temp_dir: Path,
        mock_mcp_client: MagicMock,
    ) -> None:
        """测试文件系统模式执行"""
        agent = RegSearchSubagent(
            mcp_client=mock_mcp_client,
            use_file_system=True,
            project_root=temp_dir,
        )

        # 写入任务文件
        task_path = temp_dir / "subagents" / "regsearch" / "scratch" / "current_task.md"
        task_path.write_text("# 测试任务\n查询母线失压处理方法")

        context = SubagentContext(
            query="母线失压处理",
            reg_id="angui_2024",
        )
        result = await agent.execute(context)

        # 验证结果文件被写入
        result_path = temp_dir / "subagents" / "regsearch" / "scratch" / "results.json"
        assert result_path.exists()

        report_path = temp_dir / "subagents" / "regsearch" / "scratch" / "final_report.md"
        assert report_path.exists()

    @pytest.mark.asyncio
    async def test_execute_with_chapter_scope(self, mock_mcp_client: MagicMock) -> None:
        """测试带章节范围的执行"""
        agent = RegSearchSubagent(mcp_client=mock_mcp_client)
        context = SubagentContext(
            query="失压处理",
            reg_id="angui_2024",
            chapter_scope="第六章",
        )
        result = await agent.execute(context)
        assert result.success is True

        # 验证 smart_search 调用包含 chapter_scope
        call_args = mock_mcp_client.call_tool.call_args_list
        smart_search_calls = [c for c in call_args if c[0][0] == "smart_search"]
        if smart_search_calls:
            params = smart_search_calls[0][0][1]
            assert params.get("chapter_scope") == "第六章"

    @pytest.mark.asyncio
    async def test_execute_with_hints(self, mock_mcp_client: MagicMock) -> None:
        """测试带提示的执行"""
        agent = RegSearchSubagent(mcp_client=mock_mcp_client)
        context = SubagentContext(
            query="表6-2内容",
            reg_id="angui_2024",
            hints={"page_hint": 45, "table_hint": "表6-2"},
        )
        result = await agent.execute(context)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_reset(self) -> None:
        """测试重置状态"""
        agent = RegSearchSubagent()
        agent._tool_calls.append({"tool": "test"})
        agent._sources.append("test_source")

        await agent.reset()

        assert len(agent._tool_calls) == 0
        assert len(agent._sources) == 0

    def test_register_internal_agent(self) -> None:
        """测试注册内部组件"""
        agent = RegSearchSubagent()
        mock_internal = MagicMock()

        agent.register_internal_agent("search", mock_internal)

        assert agent.get_internal_agent("search") is mock_internal
        assert agent.get_internal_agent("table") is None

    def test_log_with_file_system(self, temp_dir: Path) -> None:
        """测试文件系统模式日志"""
        agent = RegSearchSubagent(
            use_file_system=True,
            project_root=temp_dir,
        )
        agent.log("Test log message")

        log_path = temp_dir / "subagents" / "regsearch" / "logs" / "agent.log"
        assert log_path.exists()
        assert "Test log message" in log_path.read_text()

    def test_log_without_file_system(self, caplog) -> None:
        """测试非文件系统模式日志"""
        agent = RegSearchSubagent()
        # 应该使用 loguru，不会抛出异常
        agent.log("Test log message")


class TestRegSearchSubagentAggregation:
    """RegSearchSubagent 结果聚合测试"""

    def test_aggregate_empty_results(self) -> None:
        """测试空结果聚合"""
        agent = RegSearchSubagent()
        content = agent._aggregate_results([])
        assert content == "未找到相关内容"

    def test_aggregate_dict_results(self) -> None:
        """测试字典结果聚合"""
        agent = RegSearchSubagent()
        results = [
            {"content": "内容1"},
            {"content": "内容2"},
        ]
        content = agent._aggregate_results(results)
        assert "内容1" in content
        assert "内容2" in content

    def test_aggregate_nested_results(self) -> None:
        """测试嵌套结果聚合"""
        agent = RegSearchSubagent()
        results = [
            {
                "results": [
                    {"content": "嵌套内容1"},
                    {"content": "嵌套内容2"},
                ]
            }
        ]
        content = agent._aggregate_results(results)
        assert "嵌套内容1" in content
        assert "嵌套内容2" in content

    def test_aggregate_string_results(self) -> None:
        """测试字符串结果聚合"""
        agent = RegSearchSubagent()
        results = ["字符串结果1", "字符串结果2"]
        content = agent._aggregate_results(results)
        assert "字符串结果1" in content
        assert "字符串结果2" in content


class TestRegSearchSubagentToolCalls:
    """RegSearchSubagent 工具调用测试"""

    @pytest.fixture
    def mock_mcp_client(self) -> MagicMock:
        """创建模拟 MCP 客户端"""
        client = MagicMock()
        client.call_tool = AsyncMock(side_effect=[
            {"chapters": [{"title": "第六章"}]},  # get_toc
            {"results": [{"content": "搜索结果", "source": "P10"}]},  # smart_search
        ])
        return client

    @pytest.mark.asyncio
    async def test_tool_call_recording(self, mock_mcp_client: MagicMock) -> None:
        """测试工具调用记录"""
        agent = RegSearchSubagent(mcp_client=mock_mcp_client)
        context = SubagentContext(
            query="测试",
            reg_id="angui_2024",
        )
        result = await agent.execute(context)

        assert len(result.tool_calls) > 0
        tool_names = [tc["tool_name"] for tc in result.tool_calls]
        assert "get_toc" in tool_names or "smart_search" in tool_names

    @pytest.mark.asyncio
    async def test_tool_call_with_duration(self, mock_mcp_client: MagicMock) -> None:
        """测试工具调用耗时记录"""
        agent = RegSearchSubagent(mcp_client=mock_mcp_client)
        context = SubagentContext(
            query="测试",
            reg_id="angui_2024",
        )
        result = await agent.execute(context)

        for tc in result.tool_calls:
            assert "duration_ms" in tc
            assert tc["duration_ms"] >= 0
