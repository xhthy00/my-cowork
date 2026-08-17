"""Assistants scene catalog + rules injection + scene skills."""

from __future__ import annotations

from app.assistants import BUILTIN, get_assistant, load_assistants
from app.orchestrator.task_manager import _assistant_skill_prefix
from app.skills import find_skill


REQUIRED_SCENE_IDS = {
    "dashboard-creator",
    "word-form-creator",
    "financial-model-creator",
    "china-legal-counsel",
    "official-document-writing",
}

REQUIRED_CATEGORIES = {
    "presentation",
    "document",
    "spreadsheet",
    "general",
    "legal",
}

SCENE_SKILLS = (
    "officecli-data-dashboard",
    "officecli-word-form",
    "officecli-financial-model",
)


def test_assistants_scene_catalog(tmp_path):
    items = load_assistants(path=tmp_path / "missing.json")
    ids = {a["id"] for a in items}
    assert len(items) >= 9
    assert REQUIRED_SCENE_IDS.issubset(ids)
    for a in items:
        assert a.get("category") in REQUIRED_CATEGORIES
        assert isinstance(a.get("prompts"), list)
        assert a.get("rules")


def test_builtin_categories_cover_all():
    cats = {a["category"] for a in BUILTIN}
    assert cats == REQUIRED_CATEGORIES


def test_assistant_rules_injected_in_prefix():
    a = get_assistant("financial-model-creator")
    assert a is not None
    prefix = _assistant_skill_prefix(
        "financial-model-creator",
        list(a["enabled_skills"]),
    )
    assert "<assistant_rules id=\"financial-model-creator\">" in prefix
    assert "officecli-financial-model" in prefix
    assert "[assistant:financial-model-creator]" in prefix


def test_assistant_prefix_without_id_skips_rules():
    prefix = _assistant_skill_prefix(None, ["officecli"])
    assert "<assistant_rules" not in prefix
    assert "preloaded_skill" in prefix or "not found" in prefix


def test_scene_skills_discoverable():
    for sid in SCENE_SKILLS:
        meta = find_skill(sid)
        assert meta is not None, sid
        assert meta.name == sid or meta.id == sid
        assert meta.prompt and len(meta.prompt) > 100
