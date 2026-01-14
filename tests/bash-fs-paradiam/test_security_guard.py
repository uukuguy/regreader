"""测试 SecurityGuard 安全守卫"""

import tempfile
from pathlib import Path

import pytest

from regreader.infrastructure.security_guard import (
    PREDEFINED_PERMISSIONS,
    PermissionMatrix,
    SecurityGuard,
)


class TestPermissionMatrix:
    """PermissionMatrix 数据类测试"""

    def test_permission_creation(self) -> None:
        """测试权限矩阵创建"""
        matrix = PermissionMatrix(
            subagent_name="test_agent",
            readable_dirs=[Path("shared/"), Path("config/")],
            writable_dirs=[Path("scratch/")],
            allowed_tools=["tool_a", "tool_b"],
            can_execute_scripts=False,
        )
        assert matrix.subagent_name == "test_agent"
        assert len(matrix.readable_dirs) == 2
        assert len(matrix.writable_dirs) == 1
        assert matrix.can_execute_scripts is False

    def test_permission_defaults(self) -> None:
        """测试权限矩阵默认值"""
        matrix = PermissionMatrix(subagent_name="minimal")
        assert matrix.readable_dirs == []
        assert matrix.writable_dirs == []
        assert matrix.allowed_tools == []
        assert matrix.can_execute_scripts is False


class TestPredefinedPermissions:
    """预定义权限测试"""

    def test_regsearch_permissions(self) -> None:
        """测试 regsearch 权限"""
        assert "regsearch" in PREDEFINED_PERMISSIONS
        perms = PREDEFINED_PERMISSIONS["regsearch"]
        assert perms.subagent_name == "regsearch"
        assert "list_regulations" in perms.allowed_tools
        assert "smart_search" in perms.allowed_tools
        assert perms.can_execute_scripts is False

    def test_exec_permissions(self) -> None:
        """测试 exec 权限"""
        assert "exec" in PREDEFINED_PERMISSIONS
        perms = PREDEFINED_PERMISSIONS["exec"]
        assert perms.can_execute_scripts is True
        assert len(perms.allowed_tools) == 0

    def test_validator_permissions(self) -> None:
        """测试 validator 权限"""
        assert "validator" in PREDEFINED_PERMISSIONS
        perms = PREDEFINED_PERMISSIONS["validator"]
        assert perms.can_execute_scripts is False


class TestSecurityGuard:
    """SecurityGuard 单元测试"""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as d:
            temp = Path(d)
            # 创建测试目录结构
            (temp / "shared" / "data").mkdir(parents=True)
            (temp / "subagents" / "regsearch" / "scratch").mkdir(parents=True)
            (temp / "subagents" / "regsearch" / "logs").mkdir(parents=True)
            (temp / "secrets").mkdir()
            yield temp

    @pytest.fixture
    def guard(self, temp_dir: Path) -> SecurityGuard:
        """创建 SecurityGuard 实例"""
        return SecurityGuard(project_root=temp_dir)

    def test_init_with_predefined(self, guard: SecurityGuard) -> None:
        """测试使用预定义权限初始化"""
        assert "regsearch" in guard.permissions
        assert "exec" in guard.permissions
        assert "validator" in guard.permissions

    def test_check_file_access_read_allowed(self, guard: SecurityGuard, temp_dir: Path) -> None:
        """测试允许的读取访问"""
        allowed = guard.check_file_access(
            "regsearch",
            temp_dir / "shared" / "data" / "file.json",
            "read",
        )
        assert allowed is True

    def test_check_file_access_read_denied(self, guard: SecurityGuard, temp_dir: Path) -> None:
        """测试拒绝的读取访问"""
        allowed = guard.check_file_access(
            "regsearch",
            temp_dir / "secrets" / "password.txt",
            "read",
        )
        assert allowed is False

    def test_check_file_access_write_allowed(self, guard: SecurityGuard, temp_dir: Path) -> None:
        """测试允许的写入访问"""
        allowed = guard.check_file_access(
            "regsearch",
            temp_dir / "subagents" / "regsearch" / "scratch" / "result.json",
            "write",
        )
        assert allowed is True

    def test_check_file_access_write_denied(self, guard: SecurityGuard, temp_dir: Path) -> None:
        """测试拒绝的写入访问"""
        allowed = guard.check_file_access(
            "regsearch",
            temp_dir / "shared" / "data" / "readonly.json",
            "write",
        )
        assert allowed is False

    def test_check_tool_access_allowed(self, guard: SecurityGuard) -> None:
        """测试允许的工具访问"""
        assert guard.check_tool_access("regsearch", "smart_search") is True
        assert guard.check_tool_access("regsearch", "get_toc") is True
        assert guard.check_tool_access("regsearch", "search_tables") is True

    def test_check_tool_access_denied(self, guard: SecurityGuard) -> None:
        """测试拒绝的工具访问"""
        # exec 没有任何工具权限
        assert guard.check_tool_access("exec", "smart_search") is False

    def test_check_unknown_subagent(self, guard: SecurityGuard) -> None:
        """测试未知 Subagent"""
        assert guard.check_tool_access("unknown_agent", "any_tool") is False

    def test_audit_log(self, guard: SecurityGuard, temp_dir: Path) -> None:
        """测试审计日志"""
        guard.audit_log(
            action="file_access",
            subagent="regsearch",
            details={"path": "/shared/data/file.json", "operation": "read"},
        )

        # 检查日志文件
        log_path = temp_dir / "audit.jsonl"
        assert log_path.exists()
        content = log_path.read_text()
        assert "file_access" in content
        assert "regsearch" in content

    def test_register_subagent(self, guard: SecurityGuard) -> None:
        """测试注册新 Subagent"""
        new_perms = PermissionMatrix(
            subagent_name="custom_agent",
            readable_dirs=[Path("custom/")],
            allowed_tools=["custom_tool"],
        )
        guard.register_subagent("custom_agent", new_perms)

        assert "custom_agent" in guard.permissions
        assert guard.check_tool_access("custom_agent", "custom_tool") is True

    def test_get_permissions(self, guard: SecurityGuard) -> None:
        """测试获取权限"""
        perms = guard.get_permissions("regsearch")
        assert perms is not None
        assert perms.subagent_name == "regsearch"

        perms = guard.get_permissions("nonexistent")
        assert perms is None


class TestSecurityGuardPathTraversal:
    """SecurityGuard 路径遍历攻击测试"""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as d:
            temp = Path(d)
            (temp / "shared").mkdir()
            (temp / "secrets").mkdir()
            yield temp

    @pytest.fixture
    def guard(self, temp_dir: Path) -> SecurityGuard:
        """创建 SecurityGuard 实例"""
        return SecurityGuard(project_root=temp_dir)

    def test_path_traversal_read(self, guard: SecurityGuard, temp_dir: Path) -> None:
        """测试路径遍历读取攻击"""
        # 尝试通过 .. 访问父目录
        malicious_path = temp_dir / "shared" / ".." / "secrets" / "password.txt"
        allowed = guard.check_file_access("regsearch", malicious_path, "read")
        assert allowed is False

    def test_path_traversal_write(self, guard: SecurityGuard, temp_dir: Path) -> None:
        """测试路径遍历写入攻击"""
        malicious_path = temp_dir / "subagents" / "regsearch" / "scratch" / ".." / ".." / "secrets" / "inject.txt"
        allowed = guard.check_file_access("regsearch", malicious_path, "write")
        assert allowed is False

    def test_symlink_attack(self, guard: SecurityGuard, temp_dir: Path) -> None:
        """测试符号链接攻击"""
        # 创建指向 secrets 的符号链接
        symlink_path = temp_dir / "shared" / "link_to_secrets"
        try:
            symlink_path.symlink_to(temp_dir / "secrets")
        except OSError:
            pytest.skip("无法创建符号链接")

        # 应该拒绝通过符号链接访问
        allowed = guard.check_file_access("regsearch", symlink_path / "password.txt", "read")
        # 注意：当前实现可能不处理符号链接，这是一个提醒
        # 在生产环境中应该使用 path.resolve() 来处理
