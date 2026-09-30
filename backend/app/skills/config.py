"""Skills config (Eigent-shaped) + disk yaml discovery."""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from app.skills import SkillMeta, discover_skills, find_skill, load_skill_yaml
from app.skills import default_user_skills_root


def default_skills_config_path() -> Path:
    return Path.home() / ".my-cowork" / "skills-config.json"


def default_skills_root() -> Path:
    return default_user_skills_root()


def load_skills_config(path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else default_skills_config_path()
    if not p.is_file():
        return {"version": 1, "skills": {}}
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"version": 1, "skills": {}}
    skills = data.get("skills") or {}
    return {"version": int(data.get("version") or 1), "skills": dict(skills)}


def save_skills_config(data: dict[str, Any], path: str | Path | None = None) -> Path:
    p = Path(path) if path else default_skills_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": int(data.get("version") or 1), "skills": data.get("skills") or {}}
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def _default_entry() -> dict[str, Any]:
    return {
        "enabled": True,
        "scope": {"isGlobal": True, "selectedAgents": []},
        "addedAt": 0,
        "isExample": False,
    }


def merge_skill_view(
    meta: SkillMeta,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    entry = cfg.get("skills", {}).get(meta.id) or _default_entry()
    scope = entry.get("scope") or {"isGlobal": True, "selectedAgents": []}
    if isinstance(scope, str):
        scope = {"isGlobal": scope == "global", "selectedAgents": []}
    return {
        "id": meta.id,
        "name": meta.name,
        "description": meta.description,
        "schedule": meta.schedule,
        "allowed_tools": meta.allowed_tools,
        "enabled": bool(entry.get("enabled", True)),
        "scope": {
            "isGlobal": bool(scope.get("isGlobal", True)),
            "selectedAgents": list(scope.get("selectedAgents") or []),
        },
        "isExample": bool(meta.is_example or entry.get("isExample")),
        "path": str(meta.path) if meta.path else None,
    }


def list_skills_api(
    root: Path | None = None,
    config_path: Path | None = None,
) -> list[dict[str, Any]]:
    cfg = load_skills_config(config_path)
    return [merge_skill_view(s, cfg) for s in discover_skills(root)]


def patch_skill_config(
    skill_id: str,
    patch: dict[str, Any],
    config_path: Path | None = None,
) -> dict[str, Any]:
    cfg = load_skills_config(config_path)
    skills = cfg.setdefault("skills", {})
    entry = dict(skills.get(skill_id) or _default_entry())
    if "enabled" in patch:
        entry["enabled"] = bool(patch["enabled"])
    if "scope" in patch and isinstance(patch["scope"], dict):
        entry["scope"] = {
            "isGlobal": bool(patch["scope"].get("isGlobal", True)),
            "selectedAgents": list(patch["scope"].get("selectedAgents") or []),
        }
    skills[skill_id] = entry
    save_skills_config(cfg, config_path)
    meta = find_skill(skill_id)
    if meta is None:
        return {"id": skill_id, **entry}
    return merge_skill_view(meta, cfg)


def skill_visible_for_agent(skill: dict[str, Any], agent_id: str) -> bool:
    if not skill.get("enabled", True):
        return False
    scope = skill.get("scope") or {}
    if scope.get("isGlobal", True):
        return True
    return agent_id in (scope.get("selectedAgents") or [])


def import_skill_zip(
    zip_bytes: bytes,
    root: Path | None = None,
) -> SkillMeta:
    """Import a zip containing ``skill.yaml`` or ``SKILL.md``."""
    base = root or default_skills_root()
    base.mkdir(parents=True, exist_ok=True)
    import io
    import tempfile

    from app.skills import load_skill_md

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            zf.extractall(tmp_path)
        yaml_paths = list(tmp_path.rglob("skill.yaml"))
        md_paths = list(tmp_path.rglob("SKILL.md"))
        if yaml_paths:
            src = yaml_paths[0]
            meta = load_skill_yaml(src)
            src_dir = src.parent
        elif md_paths:
            src = md_paths[0]
            meta = load_skill_md(src)
            src_dir = src.parent
        else:
            raise ValueError("zip must contain skill.yaml or SKILL.md")
        dest = base / meta.id
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        for item in src_dir.iterdir():
            target = dest / item.name
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
        if (dest / "skill.yaml").is_file():
            return load_skill_yaml(dest / "skill.yaml")
        return load_skill_md(dest / "SKILL.md")


def delete_skill(skill_id: str, root: Path | None = None, config_path: Path | None = None) -> bool:
    meta = find_skill(skill_id, root=root)
    if meta is None:
        return False
    if meta.is_example:
        return False  # Bundled example skills are read-only
    dest = meta.base_dir
    if dest is None or not dest.is_dir():
        base = root or default_skills_root()
        dest = base / skill_id
    if not dest.is_dir():
        return False
    shutil.rmtree(dest)
    cfg = load_skills_config(config_path)
    if skill_id in (cfg.get("skills") or {}):
        del cfg["skills"][skill_id]
        save_skills_config(cfg, config_path)
    return True
