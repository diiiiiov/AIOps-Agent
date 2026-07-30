"""Skill 加载器：从 skills/ 目录加载 agent 定义和提示词。

目录结构：
    skills/
      agents/         # Agent 定义 (YAML)
        log.yaml
        monitor.yaml
        knowledge.yaml
      prompts/        # 系统提示词 (Markdown)
        specialist.md
        cross_validate.md
        planner.md
        replanner.md
        response.md
        executor.md
        rag_system.md
      diagnosis/      # 诊断任务模板 (Markdown)
        diagnosis_task.md

用法：
    from app.agent.skill_loader import load_agent_definitions, load_prompt

    agents = load_agent_definitions()           # -> dict[str, dict]
    prompt = load_prompt("cross_validate")      # -> str
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from string import Formatter
from typing import Any

import yaml
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

# skills/ 目录位于项目根目录（即 app/ 的上一级）
_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"
_RESOURCE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_PROMPT_FIELDS: dict[str, set[str]] = {
    "specialist": {"definition_prompt"},
    "planner": {"tools_description", "experience_context"},
    "replanner": {"tools_description"},
    "cross_validate": set(),
    "executor": set(),
    "response": set(),
    "rag_system": set(),
}


class AgentDefinition(BaseModel):
    """Validated configuration for one specialist agent."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1)
    task: str = Field(min_length=1)
    model_setting: str = Field(pattern=r"^aiops_[a-z0-9_]+_model$")
    max_iterations: int = Field(ge=1, le=20)
    max_tool_calls: int | None = Field(default=None, ge=1, le=100)
    tool_names: set[str] = Field(min_length=1)
    prompt: str = Field(min_length=1)

    @field_validator("label", "task", "prompt")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("tool_names")
    @classmethod
    def _validate_tool_names(cls, value: set[str]) -> set[str]:
        if any(not name or not _RESOURCE_NAME.fullmatch(name) for name in value):
            raise ValueError("tool_names must contain valid snake_case names")
        return value


def _ensure_skills_dir() -> Path:
    """返回 skills/ 目录路径，如果不存在则发出警告。"""
    if not _SKILLS_DIR.exists():
        logger.warning("skills 目录不存在: {}", _SKILLS_DIR)
    return _SKILLS_DIR


@lru_cache(maxsize=1)
def load_agent_definitions() -> dict[str, dict[str, Any]]:
    """从 skills/agents/*.yaml 加载所有 agent 定义。

    每个 YAML 文件应包含以下字段：
        name: str          # agent 标识符（用作字典 key）
        label: str         # 显示名称
        task: str          # 任务描述
        tool_names: list   # 工具白名单
        model_setting: str # 对应的配置项名称
        prompt: str        # 系统提示词

    Returns:
        以 name 为 key、定义字典为 value 的字典。
    """
    agents_dir = _ensure_skills_dir() / "agents"
    definitions: dict[str, dict[str, Any]] = {}

    if not agents_dir.exists():
        raise FileNotFoundError(f"skills/agents 目录不存在: {agents_dir}")

    for yaml_file in sorted(agents_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            definition = AgentDefinition.model_validate(data)
            if definition.name in definitions:
                raise ValueError(f"agent name 重复: {definition.name}")
            definitions[definition.name] = definition.model_dump()
            logger.debug("已加载 agent 定义: {} ({})", definition.name, yaml_file.name)
        except (OSError, yaml.YAMLError, ValidationError, ValueError) as exc:
            raise RuntimeError(f"加载 agent 定义失败 {yaml_file}: {exc}") from exc

    if not definitions:
        raise RuntimeError(f"skills/agents 中没有有效的 agent 定义: {agents_dir}")

    logger.info("从 skills/agents/ 加载了 {} 个 agent 定义", len(definitions))
    return definitions


@lru_cache(maxsize=32)
def load_prompt(name: str) -> str:
    """从 skills/prompts/{name}.md 加载提示词文本。

    Args:
        name: 提示词名称（不含扩展名）。

    Returns:
        提示词文本（已去除首尾空白）。

    Raises:
        FileNotFoundError: 如果提示词文件不存在。
    """
    if not _RESOURCE_NAME.fullmatch(name):
        raise ValueError(f"无效的提示词名称: {name!r}")
    prompt_file = _ensure_skills_dir() / "prompts" / f"{name}.md"
    if not prompt_file.exists():
        raise FileNotFoundError(f"提示词文件不存在: {prompt_file}")
    prompt = prompt_file.read_text(encoding="utf-8").strip()
    if not prompt:
        raise ValueError(f"提示词文件为空: {prompt_file}")

    expected_fields = _PROMPT_FIELDS.get(name)
    if expected_fields is not None:
        try:
            actual_fields = {
                field_name
                for _, field_name, _, _ in Formatter().parse(prompt)
                if field_name
            }
        except ValueError as exc:
            raise ValueError(f"提示词占位符格式错误 {prompt_file}: {exc}") from exc
        if actual_fields != expected_fields:
            raise ValueError(
                f"提示词占位符不匹配 {prompt_file}: "
                f"expected={sorted(expected_fields)}, actual={sorted(actual_fields)}"
            )
    return prompt


def load_diagnosis_template(name: str = "diagnosis_task") -> str:
    """从 skills/diagnosis/{name}.md 加载诊断任务模板。

    模板中可包含 {target} 等 Python format 占位符，
    由调用方通过 .format() 填充。

    Args:
        name: 模板名称（不含扩展名），默认 "diagnosis_task"。

    Returns:
        模板文本（已去除首尾空白）。

    Raises:
        FileNotFoundError: 如果模板文件不存在。
    """
    if not _RESOURCE_NAME.fullmatch(name):
        raise ValueError(f"无效的诊断模板名称: {name!r}")
    template_file = _ensure_skills_dir() / "diagnosis" / f"{name}.md"
    if not template_file.exists():
        raise FileNotFoundError(f"诊断模板文件不存在: {template_file}")
    return template_file.read_text(encoding="utf-8").strip()


def reload() -> None:
    """清除缓存，强制重新加载所有 skill 文件。

    在开发环境修改了 skill 文件后可调用此方法热刷新。
    生产环境中 skill 文件在启动时加载一次即可。
    """
    load_agent_definitions.cache_clear()
    load_prompt.cache_clear()
    logger.info("skill 缓存已清除，下次访问将重新加载")
