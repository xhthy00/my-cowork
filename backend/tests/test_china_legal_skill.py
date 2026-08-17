"""China legal counsel skill vendored under example-skills."""

from __future__ import annotations

from pathlib import Path

from app.assistants import get_assistant, load_assistants
from app.orchestrator.task_manager import _assistant_skill_prefix
from app.skills import find_skill, repo_root


def test_china_legal_skill_on_disk():
    root = (
        repo_root()
        / "resources"
        / "example-skills"
        / "china-legal-counsel"
    )
    assert (root / "SKILL.md").is_file()
    assert (root / "knowledge-base").is_dir()
    assert (root / "scripts" / "kb_search.py").is_file()
    text = (root / "SKILL.md").read_text(encoding="utf-8")
    assert "/Users/suze/.codex/skills" not in text
    assert "knowledge-base/" in text


def test_find_skill_china_legal_counsel():
    meta = find_skill("china-legal-counsel")
    assert meta is not None
    assert meta.id == "china-legal-counsel" or meta.name == "china-legal-counsel"
    assert meta.prompt and len(meta.prompt) > 200
    assert meta.base_dir is not None
    assert Path(meta.base_dir).name == "china-legal-counsel"


def test_assistant_seed_legal(tmp_path):
    items = load_assistants(path=tmp_path / "missing.json")
    a = next(x for x in items if x["id"] == "china-legal-counsel")
    assert a["category"] == "legal"
    assert a["enabled_skills"] == ["china-legal-counsel"]
    assert a.get("rules")
    assert len(a.get("prompts") or []) >= 1

    got = get_assistant("china-legal-counsel")
    assert got is not None
    prefix = _assistant_skill_prefix(
        "china-legal-counsel", list(got["enabled_skills"])
    )
    assert '<assistant_rules id="china-legal-counsel">' in prefix
    assert "china-legal-counsel" in prefix
