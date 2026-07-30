from pathlib import Path

import pytest

from app.agent import skill_loader


def _set_skills_dir(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(skill_loader, "_SKILLS_DIR", tmp_path)
    skill_loader.reload()
    return tmp_path


def test_load_agent_definitions_validates_required_fields(monkeypatch, tmp_path):
    skills_dir = _set_skills_dir(monkeypatch, tmp_path)
    agents_dir = skills_dir / "agents"
    agents_dir.mkdir()
    (agents_dir / "broken.yaml").write_text("name: broken\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="加载 agent 定义失败"):
        skill_loader.load_agent_definitions()


def test_load_prompt_rejects_wrong_placeholders(monkeypatch, tmp_path):
    skills_dir = _set_skills_dir(monkeypatch, tmp_path)
    prompts_dir = skills_dir / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "specialist.md").write_text("{wrong_field}", encoding="utf-8")

    with pytest.raises(ValueError, match="占位符不匹配"):
        skill_loader.load_prompt("specialist")


def test_load_prompt_rejects_path_traversal(monkeypatch, tmp_path):
    _set_skills_dir(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="无效的提示词名称"):
        skill_loader.load_prompt("../secret")
