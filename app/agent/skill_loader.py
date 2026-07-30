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

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

# skills/ 目录位于项目根目录（即 app/ 的上一级）
_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"


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
        logger.error("skills/agents 目录不存在: {}", agents_dir)
        return definitions

    for yaml_file in sorted(agents_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            if not data or "name" not in data:
                logger.warning("跳过无效的 agent 定义文件: {}", yaml_file)
                continue
            # tool_names 在 YAML 中是 list，转为 set 以兼容原有代码
            if "tool_names" in data and isinstance(data["tool_names"], list):
                data["tool_names"] = set(data["tool_names"])
            definitions[data["name"]] = data
            logger.debug("已加载 agent 定义: {} ({})", data["name"], yaml_file.name)
        except Exception as exc:
            logger.error("加载 agent 定义失败 {}: {}", yaml_file, exc)

    logger.info("从 skills/agents/ 加载了 {} 个 agent 定义", len(definitions))
    return definitions


def load_prompt(name: str) -> str:
    """从 skills/prompts/{name}.md 加载提示词文本。

    Args:
        name: 提示词名称（不含扩展名）。

    Returns:
        提示词文本（已去除首尾空白）。

    Raises:
        FileNotFoundError: 如果提示词文件不存在。
    """
    prompt_file = _ensure_skills_dir() / "prompts" / f"{name}.md"
    if not prompt_file.exists():
        raise FileNotFoundError(f"提示词文件不存在: {prompt_file}")
    return prompt_file.read_text(encoding="utf-8").strip()


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
    logger.info("skill 缓存已清除，下次访问将重新加载")
