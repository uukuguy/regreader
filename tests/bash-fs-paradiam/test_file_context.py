"""测试 FileContext 文件上下文管理器"""

import tempfile
from pathlib import Path

import pytest

from regreader.infrastructure.file_context import FileContext


class TestFileContext:
    """FileContext 单元测试"""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as d:
            temp = Path(d)
            # 创建基本目录结构
            (temp / "subagents" / "regsearch" / "scratch").mkdir(parents=True)
            (temp / "subagents" / "regsearch" / "logs").mkdir(parents=True)
            (temp / "shared" / "data").mkdir(parents=True)
            (temp / "coordinator").mkdir(parents=True)
            yield temp

    @pytest.fixture
    def file_context(self, temp_dir: Path) -> FileContext:
        """创建 FileContext 实例"""
        base_dir = temp_dir / "subagents" / "regsearch"
        return FileContext(
            subagent_name="regsearch",
            base_dir=base_dir,
            can_read=[
                temp_dir / "shared",
                temp_dir / "coordinator",
            ],
            can_write=[
                base_dir / "scratch",
                base_dir / "logs",
            ],
            project_root=temp_dir,
        )

    def test_init(self, file_context: FileContext) -> None:
        """测试初始化"""
        assert file_context.subagent_name == "regsearch"
        assert file_context.base_dir.name == "regsearch"

    def test_write_scratch(self, file_context: FileContext) -> None:
        """测试写入 scratch 目录"""
        path = file_context.write_scratch("test.txt", "Hello, World!")
        assert path.exists()
        assert path.read_text() == "Hello, World!"

    def test_read_scratch(self, file_context: FileContext) -> None:
        """测试读取 scratch 目录"""
        file_context.write_scratch("test.md", "# Test Content")
        content = file_context.read_scratch("test.md")
        assert content == "# Test Content"

    def test_read_scratch_not_found(self, file_context: FileContext) -> None:
        """测试读取不存在的文件"""
        content = file_context.read_scratch("nonexistent.txt")
        assert content is None

    def test_write_and_read_skill(self, file_context: FileContext) -> None:
        """测试 SKILL.md 读写"""
        skill_content = "# RegSearch Skills\n\n## Tools\n- smart_search"
        skill_path = file_context.base_dir / "SKILL.md"
        skill_path.write_text(skill_content, encoding="utf-8")

        content = file_context.read_skill()
        assert "RegSearch Skills" in content
        assert "smart_search" in content

    def test_log(self, file_context: FileContext) -> None:
        """测试日志写入"""
        file_context.log("Test log message")
        log_path = file_context.base_dir / "logs" / "agent.log"
        assert log_path.exists()
        log_content = log_path.read_text()
        assert "Test log message" in log_content

    def test_read_shared(self, file_context: FileContext, temp_dir: Path) -> None:
        """测试读取共享资源"""
        shared_file = temp_dir / "shared" / "config.yaml"
        shared_file.write_text("key: value", encoding="utf-8")

        content = file_context.read_shared("config.yaml")
        assert content == "key: value"

    def test_read_shared_access_denied(self, file_context: FileContext, temp_dir: Path) -> None:
        """测试读取未授权的共享资源"""
        # 创建一个不在可读列表中的文件
        secret_dir = temp_dir / "secrets"
        secret_dir.mkdir()
        (secret_dir / "password.txt").write_text("secret123")

        # 尝试读取应该失败
        with pytest.raises(PermissionError):
            file_context.read_shared("../secrets/password.txt")

    def test_check_read_access(self, file_context: FileContext, temp_dir: Path) -> None:
        """测试读取权限检查"""
        # 可读的路径
        assert file_context._check_read_access(temp_dir / "shared" / "data")
        assert file_context._check_read_access(temp_dir / "coordinator")

        # 不可读的路径
        assert not file_context._check_read_access(temp_dir / "secrets")

    def test_check_write_access(self, file_context: FileContext) -> None:
        """测试写入权限检查"""
        # 可写的路径
        assert file_context._check_write_access(file_context.base_dir / "scratch")
        assert file_context._check_write_access(file_context.base_dir / "logs")

        # 不可写的路径
        assert not file_context._check_write_access(file_context.base_dir / "readonly")


class TestFileContextAsync:
    """FileContext 异步操作测试"""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as d:
            temp = Path(d)
            (temp / "subagents" / "regsearch" / "scratch").mkdir(parents=True)
            (temp / "subagents" / "regsearch" / "logs").mkdir(parents=True)
            yield temp

    @pytest.fixture
    def file_context(self, temp_dir: Path) -> FileContext:
        """创建 FileContext 实例"""
        base_dir = temp_dir / "subagents" / "regsearch"
        return FileContext(
            subagent_name="regsearch",
            base_dir=base_dir,
            can_write=[base_dir / "scratch", base_dir / "logs"],
            project_root=temp_dir,
        )

    @pytest.mark.asyncio
    async def test_async_write_scratch(self, file_context: FileContext) -> None:
        """测试异步写入"""
        path = await file_context.async_write_scratch("async_test.txt", "Async content")
        assert path.exists()
        assert path.read_text() == "Async content"

    @pytest.mark.asyncio
    async def test_async_read_scratch(self, file_context: FileContext) -> None:
        """测试异步读取"""
        file_context.write_scratch("async_read.txt", "Async read test")
        content = await file_context.async_read_scratch("async_read.txt")
        assert content == "Async read test"
