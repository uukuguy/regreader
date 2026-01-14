"""测试 SkillLoader 技能加载器"""

import tempfile
from pathlib import Path

import pytest

from regreader.infrastructure.skill_loader import Skill, SkillLoader


class TestSkill:
    """Skill 数据类测试"""

    def test_skill_creation(self) -> None:
        """测试 Skill 创建"""
        skill = Skill(
            name="test_skill",
            description="A test skill",
            entry_point="skills/test/workflow.py",
            required_tools=["tool_a", "tool_b"],
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )
        assert skill.name == "test_skill"
        assert len(skill.required_tools) == 2

    def test_skill_defaults(self) -> None:
        """测试 Skill 默认值"""
        skill = Skill(name="minimal", description="Minimal skill")
        assert skill.entry_point == ""
        assert skill.required_tools == []
        assert skill.examples == []


class TestSkillLoader:
    """SkillLoader 单元测试"""

    @pytest.fixture
    def temp_project(self) -> Path:
        """创建临时项目结构"""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)

            # 创建 skills/ 目录结构
            skills_dir = root / "skills"
            skills_dir.mkdir()

            # 创建 registry.yaml
            registry_content = """
skills:
  - name: simple_search
    description: 简单文档搜索工作流
    entry_point: skills/simple_search/workflow.py
    required_tools:
      - get_toc
      - smart_search
    subagents:
      - regsearch
    input_schema:
      type: object
      properties:
        query:
          type: string
    output_schema:
      type: object
    tags:
      - search
    version: "1.0.0"

  - name: table_lookup
    description: 表格搜索与提取
    entry_point: skills/table_lookup/workflow.py
    required_tools:
      - search_tables
      - get_table_by_id
    subagents:
      - regsearch
"""
            (skills_dir / "registry.yaml").write_text(registry_content, encoding="utf-8")

            # 创建 subagents/regsearch/SKILL.md
            subagents_dir = root / "subagents" / "regsearch"
            subagents_dir.mkdir(parents=True)
            skill_md = """# RegSearch-Subagent 技能说明

## 角色定位
规程文档检索专家

## 可用工具
- list_regulations
- get_toc
- smart_search

## 标准工作流
1. 简单查询: get_toc → smart_search
"""
            (subagents_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

            yield root

    @pytest.fixture
    def loader(self, temp_project: Path) -> SkillLoader:
        """创建 SkillLoader 实例"""
        return SkillLoader(project_root=temp_project)

    def test_load_all(self, loader: SkillLoader) -> None:
        """测试加载所有技能"""
        skills = loader.load_all()
        assert len(skills) >= 2  # 至少有 registry 中的两个
        assert "simple_search" in skills
        assert "table_lookup" in skills

    def test_get_skill(self, loader: SkillLoader) -> None:
        """测试获取单个技能"""
        loader.load_all()
        skill = loader.get_skill("simple_search")
        assert skill is not None
        assert skill.name == "simple_search"
        assert "get_toc" in skill.required_tools
        assert "smart_search" in skill.required_tools

    def test_get_skill_not_found(self, loader: SkillLoader) -> None:
        """测试获取不存在的技能"""
        loader.load_all()
        skill = loader.get_skill("nonexistent")
        assert skill is None

    def test_get_skills_for_subagent(self, loader: SkillLoader) -> None:
        """测试获取 Subagent 的技能"""
        loader.load_all()
        skills = loader.get_skills_for_subagent("regsearch")
        assert len(skills) >= 2
        assert all("regsearch" in s.subagents for s in skills)

    def test_load_from_registry(self, loader: SkillLoader, temp_project: Path) -> None:
        """测试从 registry.yaml 加载"""
        skills = loader._load_from_registry()
        assert len(skills) == 2
        assert skills[0].name == "simple_search"
        assert skills[1].name == "table_lookup"

    def test_load_from_subagent_skill_md(self, loader: SkillLoader, temp_project: Path) -> None:
        """测试从 SKILL.md 加载"""
        skills = loader._load_from_subagent_skills()
        assert len(skills) >= 1
        # 查找 regsearch 的技能
        regsearch_skills = [s for s in skills if "regsearch" in s.name.lower()]
        assert len(regsearch_skills) >= 1


class TestSkillLoaderEdgeCases:
    """SkillLoader 边界情况测试"""

    def test_empty_project(self) -> None:
        """测试空项目"""
        with tempfile.TemporaryDirectory() as d:
            loader = SkillLoader(project_root=Path(d))
            skills = loader.load_all()
            assert skills == {}

    def test_invalid_registry(self) -> None:
        """测试无效的 registry.yaml"""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            skills_dir = root / "skills"
            skills_dir.mkdir()
            (skills_dir / "registry.yaml").write_text("invalid: yaml: content:")

            loader = SkillLoader(project_root=root)
            # 应该能容错处理
            skills = loader.load_all()
            assert isinstance(skills, dict)

    def test_malformed_skill_md(self) -> None:
        """测试格式错误的 SKILL.md"""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            subagent_dir = root / "subagents" / "test"
            subagent_dir.mkdir(parents=True)
            # 写入空的 SKILL.md
            (subagent_dir / "SKILL.md").write_text("")

            loader = SkillLoader(project_root=root)
            skills = loader.load_all()
            assert isinstance(skills, dict)
