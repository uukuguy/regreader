"""SkillLoader 技能加载器

动态加载 SKILL.md 和 skills/ 目录中定义的技能包。
支持 YAML front matter 格式和 Markdown 结构解析。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from loguru import logger


class SkillNotFoundError(Exception):
    """技能未找到"""

    pass


class SkillParseError(Exception):
    """技能解析错误"""

    pass


@dataclass
class Skill:
    """技能定义

    描述一个可复用的工作流技能，包括其输入输出规范、所需工具等。

    Attributes:
        name: 技能名称
        description: 技能描述
        entry_point: 入口点（脚本路径或 Python 模块）
        required_tools: 所需 MCP 工具列表
        input_schema: 输入参数 JSON Schema
        output_schema: 输出结果 JSON Schema
        examples: 使用示例列表
        subagents: 关联的 Subagent 类型列表
        version: 技能版本
        tags: 标签列表
    """

    name: str
    """技能名称"""

    description: str
    """技能描述"""

    entry_point: str = ""
    """入口点（脚本路径或 Python 模块）"""

    required_tools: list[str] = field(default_factory=list)
    """所需 MCP 工具列表"""

    input_schema: dict[str, Any] = field(default_factory=dict)
    """输入参数 JSON Schema"""

    output_schema: dict[str, Any] = field(default_factory=dict)
    """输出结果 JSON Schema"""

    examples: list[dict[str, Any]] = field(default_factory=list)
    """使用示例列表"""

    subagents: list[str] = field(default_factory=list)
    """关联的 Subagent 类型列表"""

    version: str = "1.0.0"
    """技能版本"""

    tags: list[str] = field(default_factory=list)
    """标签列表"""

    source_path: Path | None = None
    """来源文件路径"""

    @classmethod
    def from_yaml(cls, data: dict[str, Any], source_path: Path | None = None) -> Skill:
        """从 YAML 数据创建 Skill

        Args:
            data: YAML 解析后的字典
            source_path: 来源文件路径

        Returns:
            Skill 实例
        """
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            entry_point=data.get("entry_point", ""),
            required_tools=data.get("required_tools", []),
            input_schema=data.get("input_schema", {}),
            output_schema=data.get("output_schema", {}),
            examples=data.get("examples", []),
            subagents=data.get("subagents", []),
            version=data.get("version", "1.0.0"),
            tags=data.get("tags", []),
            source_path=source_path,
        )

    @classmethod
    def from_skill_md(cls, content: str, source_path: Path | None = None) -> Skill:
        """从 SKILL.md 内容解析 Skill

        支持 YAML front matter 或纯 Markdown 格式。

        Args:
            content: SKILL.md 文件内容
            source_path: 来源文件路径

        Returns:
            Skill 实例
        """
        # 尝试解析 YAML front matter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    front_matter = yaml.safe_load(parts[1])
                    if isinstance(front_matter, dict):
                        return cls.from_yaml(front_matter, source_path)
                except yaml.YAMLError:
                    pass

        # 降级到 Markdown 解析
        return cls._parse_markdown(content, source_path)

    @classmethod
    def _parse_markdown(cls, content: str, source_path: Path | None = None) -> Skill:
        """从 Markdown 结构解析 Skill

        Args:
            content: Markdown 内容
            source_path: 来源文件路径

        Returns:
            Skill 实例
        """
        skill_data: dict[str, Any] = {
            "required_tools": [],
            "examples": [],
            "subagents": [],
            "tags": [],
        }

        # 提取标题作为名称
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if title_match:
            skill_data["name"] = title_match.group(1).strip()

        # 提取描述（第一个段落）
        desc_match = re.search(r"^#.+\n\n(.+?)(?:\n\n|$)", content, re.MULTILINE | re.DOTALL)
        if desc_match:
            skill_data["description"] = desc_match.group(1).strip()

        # 提取工具列表
        tools_section = re.search(
            r"##\s*(?:所需工具|Required Tools|工具列表)\s*\n((?:[-*]\s+.+\n?)+)",
            content,
            re.IGNORECASE,
        )
        if tools_section:
            tools = re.findall(r"[-*]\s+`?(\w+)`?", tools_section.group(1))
            skill_data["required_tools"] = tools

        # 提取内部组件（作为 subagents）
        components_section = re.search(
            r"##\s*(?:内部组件|Components|组件)\s*\n((?:[-*]\s+.+\n?)+)",
            content,
            re.IGNORECASE,
        )
        if components_section:
            components = re.findall(r"[-*]\s+(\w+)", components_section.group(1))
            skill_data["subagents"] = [c.lower() for c in components]

        return cls(**skill_data, source_path=source_path)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典

        Returns:
            技能定义字典
        """
        return {
            "name": self.name,
            "description": self.description,
            "entry_point": self.entry_point,
            "required_tools": self.required_tools,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "examples": self.examples,
            "subagents": self.subagents,
            "version": self.version,
            "tags": self.tags,
        }


class SkillLoader:
    """技能加载器

    从 skills/ 目录和 subagents/*/SKILL.md 加载技能定义。

    两级结构：
    1. subagents/*/SKILL.md - Subagent 级技能说明
    2. skills/*/SKILL.md - 工作流级可复用技能

    Attributes:
        project_root: 项目根目录
        skills_dir: skills/ 目录路径
        subagents_dir: subagents/ 目录路径
        registry_path: 技能注册表路径
    """

    def __init__(
        self,
        project_root: Path | None = None,
        skills_dir: str = "skills",
        subagents_dir: str = "subagents",
    ):
        """初始化技能加载器

        Args:
            project_root: 项目根目录
            skills_dir: skills/ 目录相对路径
            subagents_dir: subagents/ 目录相对路径
        """
        self.project_root = project_root or Path.cwd()
        self.skills_dir = self.project_root / skills_dir
        self.subagents_dir = self.project_root / subagents_dir
        self.registry_path = self.skills_dir / "registry.yaml"

        self._cache: dict[str, Skill] = {}
        self._loaded = False

    def load_all(self, force: bool = False) -> dict[str, Skill]:
        """加载所有技能

        Args:
            force: 是否强制重新加载

        Returns:
            技能名到 Skill 的映射
        """
        if self._loaded and not force:
            return self._cache

        self._cache.clear()

        # 1. 加载注册表中的技能
        self._load_from_registry()

        # 2. 扫描 skills/ 目录
        self._scan_skills_dir()

        # 3. 扫描 subagents/ 目录
        self._scan_subagents_dir()

        self._loaded = True
        logger.info(f"Loaded {len(self._cache)} skills")
        return self._cache

    def _load_from_registry(self) -> None:
        """从 registry.yaml 加载技能"""
        if not self.registry_path.exists():
            return

        try:
            content = self.registry_path.read_text(encoding="utf-8")
            registry = yaml.safe_load(content)
            if not registry or "skills" not in registry:
                return

            for skill_data in registry["skills"]:
                skill = Skill.from_yaml(skill_data, self.registry_path)
                if skill.name:
                    self._cache[skill.name] = skill
                    logger.debug(f"Loaded skill from registry: {skill.name}")
        except yaml.YAMLError as e:
            logger.warning(f"Failed to parse registry.yaml: {e}")

    def _scan_skills_dir(self) -> None:
        """扫描 skills/ 目录中的 SKILL.md 文件"""
        if not self.skills_dir.exists():
            return

        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                self._load_skill_md(skill_md, prefix="skill")

    def _scan_subagents_dir(self) -> None:
        """扫描 subagents/ 目录中的 SKILL.md 文件"""
        if not self.subagents_dir.exists():
            return

        for agent_dir in self.subagents_dir.iterdir():
            if not agent_dir.is_dir():
                continue

            skill_md = agent_dir / "SKILL.md"
            if skill_md.exists():
                self._load_skill_md(skill_md, prefix="subagent")

    def _load_skill_md(self, path: Path, prefix: str = "") -> None:
        """加载单个 SKILL.md 文件

        Args:
            path: 文件路径
            prefix: 技能名前缀
        """
        try:
            content = path.read_text(encoding="utf-8")
            skill = Skill.from_skill_md(content, path)

            # 使用目录名作为默认名称
            if not skill.name:
                skill.name = path.parent.name

            # 添加前缀以区分来源
            key = f"{prefix}:{skill.name}" if prefix else skill.name

            self._cache[key] = skill
            # 同时添加无前缀版本（如果不冲突）
            if skill.name not in self._cache:
                self._cache[skill.name] = skill

            logger.debug(f"Loaded SKILL.md: {path} -> {key}")
        except Exception as e:
            logger.warning(f"Failed to load {path}: {e}")

    def get_skill(self, name: str) -> Skill:
        """获取指定技能

        Args:
            name: 技能名称

        Returns:
            Skill 实例

        Raises:
            SkillNotFoundError: 技能不存在
        """
        if not self._loaded:
            self.load_all()

        if name not in self._cache:
            raise SkillNotFoundError(f"Skill not found: {name}")

        return self._cache[name]

    def get_skills_for_subagent(self, subagent_type: str) -> list[Skill]:
        """获取指定 Subagent 关联的技能

        Args:
            subagent_type: Subagent 类型

        Returns:
            关联的技能列表
        """
        if not self._loaded:
            self.load_all()

        return [
            skill
            for skill in self._cache.values()
            if subagent_type.lower() in [s.lower() for s in skill.subagents]
        ]

    def get_skills_by_tool(self, tool_name: str) -> list[Skill]:
        """获取使用指定工具的技能

        Args:
            tool_name: 工具名称

        Returns:
            使用该工具的技能列表
        """
        if not self._loaded:
            self.load_all()

        return [skill for skill in self._cache.values() if tool_name in skill.required_tools]

    def get_skills_by_tag(self, tag: str) -> list[Skill]:
        """获取指定标签的技能

        Args:
            tag: 标签

        Returns:
            带有该标签的技能列表
        """
        if not self._loaded:
            self.load_all()

        return [skill for skill in self._cache.values() if tag in skill.tags]

    def list_skills(self) -> list[str]:
        """列出所有技能名称

        Returns:
            技能名称列表
        """
        if not self._loaded:
            self.load_all()

        return list(self._cache.keys())

    def refresh(self) -> dict[str, Skill]:
        """刷新技能缓存

        Returns:
            刷新后的技能映射
        """
        return self.load_all(force=True)

    def __repr__(self) -> str:
        return f"SkillLoader(skills_dir={self.skills_dir}, loaded={len(self._cache)} skills)"
