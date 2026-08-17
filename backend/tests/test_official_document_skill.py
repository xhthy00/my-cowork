"""Official document writing skill vendored under example-skills."""

from __future__ import annotations

from pathlib import Path

from app.assistants import get_assistant, load_assistants
from app.orchestrator.task_manager import _assistant_skill_prefix
from app.skills import find_skill, repo_root


def test_official_document_skill_on_disk():
    root = (
        repo_root()
        / "resources"
        / "example-skills"
        / "official-document-writing"
    )
    assert (root / "SKILL.md").is_file()
    assert (root / "references" / "document-templates.md").is_file()
    assert (root / "checklists" / "quality-checklist.md").is_file()
    text = (root / "SKILL.md").read_text(encoding="utf-8")
    assert "MyCowork" in text
    assert "official-document-writing" in text
    fmt = (root / "references" / "body-manuscript-format.md").read_text(encoding="utf-8")
    assert "29磅" in fmt or "29 磅" in fmt
    assert "方正仿宋_GBK" in fmt
    assert "方正小标宋_GBK" in fmt
    assert "2.9" in fmt


def test_find_skill_official_document_writing():
    meta = find_skill("official-document-writing")
    assert meta is not None
    assert meta.id == "official-document-writing" or meta.name == "official-document-writing"
    assert meta.prompt and len(meta.prompt) > 200
    assert meta.base_dir is not None
    assert Path(meta.base_dir).name == "official-document-writing"


def test_assistant_seed_official_document(tmp_path):
    items = load_assistants(path=tmp_path / "missing.json")
    a = next(x for x in items if x["id"] == "official-document-writing")
    assert a["name"] == "公文写作助手"
    assert a["category"] == "document"
    assert "official-document-writing" in a["enabled_skills"]
    assert "officecli" in a["enabled_skills"]
    assert a.get("rules")
    assert "重新生成" in a["rules"]
    assert "generic docx" in a["rules"]
    assert len(a.get("prompts") or []) >= 1

    got = get_assistant("official-document-writing")
    assert got is not None
    prefix = _assistant_skill_prefix(
        "official-document-writing", list(got["enabled_skills"])
    )
    assert '<assistant_rules id="official-document-writing">' in prefix
    assert "official-document-writing" in prefix
