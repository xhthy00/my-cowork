"""Active skill toolkit (list_skills / load_skill) — Eigent parity."""

from __future__ import annotations

import json
from pathlib import Path

from app.skills import discover_skills, find_skill, load_skill_md
from app.skills.config import save_skills_config
from app.tools.builtin.skills import make_skill_tools


def _write_yaml_skill(root: Path, skill_id: str = "demo") -> None:
    d = root / skill_id
    d.mkdir(parents=True)
    (d / "skill.yaml").write_text(
        f"id: {skill_id}\nname: Demo\ndescription: demo skill\nprompt: DO THE DEMO\n",
        encoding="utf-8",
    )


def _write_md_skill(root: Path) -> None:
    d = root / "md-skill"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\nname: md-skill\ndescription: from markdown\n---\n\n# Body\nDo MD.\n",
        encoding="utf-8",
    )


def test_discover_yaml_and_skill_md(tmp_path: Path):
    _write_yaml_skill(tmp_path)
    _write_md_skill(tmp_path)
    skills = discover_skills(tmp_path)
    ids = {s.id for s in skills}
    assert "demo" in ids
    assert "md-skill" in ids


def test_load_skill_md_frontmatter(tmp_path: Path):
    _write_md_skill(tmp_path)
    meta = load_skill_md(tmp_path / "md-skill" / "SKILL.md")
    assert meta.id == "md-skill"
    assert "Do MD" in meta.prompt


def test_list_and_load_tools(tmp_path: Path):
    _write_yaml_skill(tmp_path)
    cfg = tmp_path / "skills-config.json"
    save_skills_config({"version": 1, "skills": {}}, cfg)
    tools = {t.name: t for t in make_skill_tools(
        "developer_agent", root=tmp_path, config_path=cfg
    )}
    listed = json.loads(tools["list_skills"].invoke({}))
    assert any(row["name"] == "demo" for row in listed)

    loaded = tools["load_skill"].invoke({"name": "demo"})
    assert "## Skill:" in loaded
    assert "DO THE DEMO" in loaded


def test_load_skill_respects_scope(tmp_path: Path):
    _write_yaml_skill(tmp_path)
    cfg = tmp_path / "skills-config.json"
    save_skills_config(
        {
            "version": 1,
            "skills": {
                "demo": {
                    "enabled": True,
                    "scope": {
                        "isGlobal": False,
                        "selectedAgents": ["document_agent"],
                    },
                }
            },
        },
        cfg,
    )
    dev_tools = {t.name: t for t in make_skill_tools(
        "developer_agent", root=tmp_path, config_path=cfg
    )}
    doc_tools = {t.name: t for t in make_skill_tools(
        "document_agent", root=tmp_path, config_path=cfg
    )}
    assert "not available" in dev_tools["load_skill"].invoke({"name": "demo"})
    assert "DO THE DEMO" in doc_tools["load_skill"].invoke({"name": "demo"})


def test_single_agent_sees_enabled_skills(tmp_path: Path):
    _write_yaml_skill(tmp_path)
    cfg = tmp_path / "skills-config.json"
    save_skills_config(
        {
            "version": 1,
            "skills": {
                "demo": {
                    "enabled": True,
                    "scope": {"isGlobal": False, "selectedAgents": []},
                }
            },
        },
        cfg,
    )
    # Scope excludes everyone but single_agent ignores scope (Eigent).
    tools = {t.name: t for t in make_skill_tools(
        "single_agent", root=tmp_path, config_path=cfg
    )}
    listed = json.loads(tools["list_skills"].invoke({}))
    assert any(row["name"] == "demo" for row in listed)


def test_find_skill_by_name(tmp_path: Path):
    _write_md_skill(tmp_path)
    assert find_skill("md-skill", root=tmp_path) is not None
