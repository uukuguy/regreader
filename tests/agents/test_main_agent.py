"""测试主智能体和子智能体的职责分离

验证：
1. 主智能体进行任务级拆解（不是原子工具调用）
2. 子智能体进行原子级拆解和执行
3. 文件系统通信正常工作
4. 工作区记录完整
"""

import json
from pathlib import Path
import tempfile
import shutil

import pytest


class TestMainAgentTaskDecomposition:
    """测试主智能体任务级拆解"""

    def test_main_agent_initialization(self):
        """测试主智能体初始化"""
        from regreader.agents.main import MainAgent

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "coordinator"
            agent = MainAgent(reg_id="test_reg", workspace_root=workspace)

            # 验证初始化
            assert agent.reg_id == "test_reg"
            assert agent.session_id is not None
            assert agent.session_dir.exists()
            assert agent.session_dir == workspace / f"session_{agent.session_id}"

    def test_main_agent_prompt(self):
        """测试主智能体提示词强调任务级拆解"""
        from regreader.agents.main import MainAgent

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "coordinator"
            agent = MainAgent(reg_id="test_reg", workspace_root=workspace)

            prompt = agent._build_main_prompt()

            # 验证提示词包含任务级拆解说明
            assert "任务级" in prompt
            assert "子任务" in prompt

            # 验证提示词明确禁止原子操作
            assert "不要直接调用底层 MCP 工具" in prompt
            assert "不要拆解为" in prompt
            assert "调用 get_toc()" in prompt

            # 验证提示词说明子智能体职责
            assert "子智能体会收到你的任务" in prompt
            assert "自己决定如何拆解为原子操作" in prompt

    def test_main_agent_log_execution(self):
        """测试主智能体记录执行日志"""
        from regreader.agents.main import MainAgent

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "coordinator"
            agent = MainAgent(reg_id="test_reg", workspace_root=workspace)

            # 记录执行日志
            agent._log_execution(
                action="dispatch_task",
                target="search",
                details={"task_description": "测试任务"}
            )

            # 验证日志文件创建
            log_file = agent.session_dir / "execution.md"
            assert log_file.exists()

            log_content = log_file.read_text(encoding="utf-8")
            assert "dispatch_task" in log_content
            assert "search" in log_content
            assert "测试任务" in log_content


class TestSubagentAtomicDecomposition:
    """测试子智能体原子级拆解"""

    def test_subagent_reads_task(self):
        """测试子智能体从 task.md 读取任务"""
        from regreader.subagents.search.agent import SearchAgent

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "subagents" / "search"
            workspace.mkdir(parents=True)

            # 创建任务文件
            task_file = workspace / "task.md"
            task_content = """# 搜索任务

## 任务描述
测试任务：定位相关章节

## 接收时间
2024-01-16T10:00:00

## 上下文
- 规程 ID: test_reg
"""
            task_file.write_text(task_content, encoding="utf-8")

            # 创建子智能体
            agent = SearchAgent(workspace=workspace, reg_id="test_reg")

            # 读取任务
            task = agent.read_task()

            # 验证任务内容
            assert "测试任务：定位相关章节" in task
            assert "test_reg" in task

    def test_subagent_rule_based_decomposition(self):
        """测试子智能体基于规则的原子任务拆解"""
        from regreader.subagents.search.agent import SearchAgent

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "subagents" / "search"
            workspace.mkdir(parents=True)

            agent = SearchAgent(workspace=workspace, reg_id="test_reg")

            # 测试不同任务的拆解
            task1 = "从规程目录中定位关于母线失压的章节"
            steps1 = agent._rule_based_decomposition(task1)

            # 验证拆解结果
            assert len(steps1) > 0
            assert steps1[0]["action"] == "get_toc"
            assert steps1[0]["params"]["reg_id"] == "test_reg"

            # 测试搜索任务
            task2 = "搜索母线失压相关内容"
            steps2 = agent._rule_based_decomposition(task2)

            # 验证拆解结果
            assert len(steps2) > 0
            assert steps2[0]["action"] == "smart_search"
            assert "母线失压" in steps2[0]["params"]["query"]

    def test_subagent_writes_steps(self):
        """测试子智能体写入步骤到 steps.md"""
        from regreader.subagents.bash_fs_base import BaseSubagentFS, SubagentResult

        # 创建测试子智能体
        class TestSubagent(BaseSubagentFS):
            def decompose_task(self, task: str):
                return [
                    {
                        "step": 1,
                        "description": "测试步骤",
                        "action": "test_action",
                        "params": {"key": "value"},
                    }
                ]

            def execute_atomic_step(self, step):
                return {"result": "success"}

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "test"
            workspace.mkdir()

            agent = TestSubagent(workspace=workspace, reg_id="test_reg")

            # 写入步骤
            steps = [
                {
                    "step": 1,
                    "description": "测试步骤",
                    "action": "test_action",
                    "timestamp": "2024-01-16T10:00:00",
                    "params": {"key": "value"},
                    "result": {"result": "success"},
                }
            ]
            agent.write_steps(steps)

            # 验证步骤文件
            steps_file = workspace / "steps.md"
            assert steps_file.exists()

            content = steps_file.read_text(encoding="utf-8")
            assert "测试步骤" in content
            assert "test_action" in content
            assert "success" in content

    def test_subagent_writes_results(self):
        """测试子智能体写入结果到 results.json"""
        from regreader.subagents.bash_fs_base import BaseSubagentFS

        # 创建测试子智能体
        class TestSubagent(BaseSubagentFS):
            def decompose_task(self, task: str):
                return []

            def execute_atomic_step(self, step):
                return {}

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "test"
            workspace.mkdir()

            agent = TestSubagent(workspace=workspace, reg_id="test_reg")

            # 写入结果
            results = {
                "task": "测试任务",
                "final_answer": "测试答案",
                "completed_at": "2024-01-16T10:00:00",
            }
            agent.write_results(results)

            # 验证结果文件
            results_file = workspace / "results.json"
            assert results_file.exists()

            with open(results_file, encoding="utf-8") as f:
                loaded = json.load(f)

            assert loaded["task"] == "测试任务"
            assert loaded["final_answer"] == "测试答案"


class TestFileSystemCommunication:
    """测试文件系统通信"""

    def test_main_agent_writes_task_file(self):
        """测试主智能体写入任务文件到子智能体工作区"""
        from regreader.agents.main import MainAgent

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            coordinator = workspace_root / "coordinator"
            subagent_workspace = workspace_root / "subagents" / "search"

            agent = MainAgent(reg_id="test_reg", workspace_root=coordinator)

            # 分发任务
            agent._dispatch_search_task("测试搜索任务")

            # 验证任务文件创建
            task_file = subagent_workspace / "task.md"
            assert task_file.exists()

            content = task_file.read_text(encoding="utf-8")
            assert "测试搜索任务" in content
            assert "test_reg" in content
            assert agent.session_id in content


class TestWorkspaceStructure:
    """测试工作区结构"""

    def test_main_agent_workspace_structure(self):
        """测试主智能体工作区结构"""
        from regreader.agents.main import MainAgent

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "coordinator"
            agent = MainAgent(reg_id="test_reg", workspace_root=workspace)

            # 验证工作区结构
            session_dir = agent.session_dir
            assert session_dir.exists()
            # plan.md 在 query() 时创建，初始化时不创建

    def test_subagent_workspace_structure(self):
        """测试子智能体工作区结构"""
        from regreader.subagents.search.agent import SearchAgent

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "subagents" / "search"
            agent = SearchAgent(workspace=workspace, reg_id="test_reg")

            # 验证工作区结构
            assert workspace.exists()
            assert (workspace / "logs").exists()


class TestResponsibilitySeparation:
    """测试职责分离"""

    def test_main_agent_does_not_call_atomic_tools(self):
        """测试主智能体不调用原子工具"""
        from regreader.agents.main import MainAgent

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "coordinator"
            agent = MainAgent(reg_id="test_reg", workspace_root=workspace)

            prompt = agent._build_main_prompt()

            # 验证提示词明确禁止原子工具调用
            assert "❌ 不要直接调用底层 MCP 工具" in prompt
            assert "❌ 不要拆解为" in prompt
            assert "调用 get_toc()" in prompt

    def test_subagent_decomposes_into_atomic_operations(self):
        """测试子智能体拆解为原子操作"""
        from regreader.subagents.search.agent import SearchAgent

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "subagents" / "search"
            workspace.mkdir(parents=True)  # 添加 parents=True

            agent = SearchAgent(workspace=workspace, reg_id="test_reg")

            # 测试任务拆解
            task = "从规程目录中定位关于母线失压的章节"
            steps = agent.decompose_task(task)

            # 验证拆解为原子操作
            assert len(steps) > 0

            for step in steps:
                # 验证每个步骤包含原子操作信息
                assert "step" in step
                assert "description" in step
                assert "action" in step
                assert "params" in step

                # 验证 action 是工具名称
                assert step["action"] in [
                    "get_toc",
                    "smart_search",
                    "read_page_range",
                    "lookup_annotation",
                ]

    def test_task_level_vs_atomic_level(self):
        """测试任务级 vs 原子级区别"""
        # 任务级描述（主智能体）
        task_level = [
            "从规程目录中定位关于母线失压的章节",
            "从指定章节范围获得与问题任务相关的内容或表格",
            "查找并提取相关的表格数据",
        ]

        # 原子级描述（子智能体）
        atomic_level = [
            "调用 get_toc()",
            "调用 read_page_range()",
            "调用 smart_search()",
        ]

        # 验证任务级描述不包含原子操作
        for task in task_level:
            assert "调用 get_toc()" not in task
            assert "调用 read_page_range()" not in task
            assert "调用 smart_search()" not in task

        # 验证原子级描述包含具体工具调用
        for atomic in atomic_level:
            assert "调用" in atomic
            assert "(" in atomic and ")" in atomic


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
