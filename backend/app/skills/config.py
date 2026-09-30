"""Skills config (Eigent-shaped) + disk yaml discovery."""

from __future__ import annotations

import json
import re
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from app.skills import SkillMeta, discover_skills, find_skill, load_skill_yaml
from app.skills import default_user_skills_root


def default_skills_config_path() -> Path:
    return Path.home() / ".my-cowork" / "skills-config.json"


def default_skills_root() -> Path:
    return default_user_skills_root()


def migrate_user_skills() -> list[str]:
    """Copy legacy skills once; preserve sources and report conflicts/failures."""
    import tempfile
    from app.skills import legacy_user_skills_roots, load_skill_md

    base = default_skills_root()
    marker = base / ".migration-v1.json"
    if marker.is_file():
        return list(json.loads(marker.read_text(encoding="utf-8")).get("warnings", []))
    base.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    failed = False
    for old in legacy_user_skills_roots():
        if not old.is_dir():
            continue
        for source in sorted(old.iterdir()):
            if source.name.startswith(("_", ".")) or not source.is_dir():
                continue
            yaml_path, md_path = source / "skill.yaml", source / "SKILL.md"
            if not yaml_path.is_file() and not md_path.is_file():
                continue
            try:
                if source.is_symlink() or source.resolve().parent != old.resolve():
                    raise ValueError("技能目录是链接")
                meta = load_skill_yaml(yaml_path) if yaml_path.is_file() else load_skill_md(md_path)
                dest = _install_target(base, meta.id)
                files = [p for p in source.rglob("*")]
                if any(p.is_symlink() or not p.resolve().is_relative_to(source.resolve()) for p in files):
                    raise ValueError("技能含有链接或目录外文件")
                if dest.exists():
                    identical = all((dest / p.relative_to(source)).is_file() and
                                    (dest / p.relative_to(source)).read_bytes() == p.read_bytes()
                                    for p in files if p.is_file())
                    if not identical:
                        warnings.append(f"技能 {meta.id} 已存在，未覆盖；旧副本保留在 {source}")
                    continue
                with tempfile.TemporaryDirectory(prefix=".migrate-", dir=base) as tmp:
                    staged = Path(tmp) / "skill"
                    shutil.copytree(source, staged)
                    if any((staged / p.relative_to(source)).read_bytes() != p.read_bytes()
                           for p in files if p.is_file()):
                        raise OSError("复制验证失败")
                    _install_target(base, meta.id)
                    staged.rename(dest)
            except (OSError, ValueError) as exc:
                failed = True
                warnings.append(f"技能 {source.name} 迁移失败，保留旧位置供读取：{exc}")
    if not failed:
        tmp_marker = marker.with_suffix(".tmp")
        tmp_marker.write_text(json.dumps({"warnings": warnings}, ensure_ascii=False), encoding="utf-8")
        tmp_marker.replace(marker)
    return warnings


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
    entry = _default_entry() if meta.app_origin else (cfg.get("skills", {}).get(meta.id) or _default_entry())
    scope = entry.get("scope") or {"isGlobal": True, "selectedAgents": []}
    if isinstance(scope, str):
        scope = {"isGlobal": scope == "global", "selectedAgents": []}
    return {
        "id": meta.id,
        "name": meta.name,
        "description": meta.description,
        "schedule": meta.schedule,
        "allowed_tools": meta.allowed_tools,
        "enabled": meta.available if meta.app_origin else bool(entry.get("enabled", True)),
        "appOrigin": meta.app_origin,
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
    *, bundled: dict[str, SkillMeta] | None = None,
) -> list[dict[str, Any]]:
    cfg = load_skills_config(config_path)
    return [merge_skill_view(s, cfg) for s in discover_skills(root, bundled=bundled)]


def patch_skill_config(
    skill_id: str,
    patch: dict[str, Any],
    config_path: Path | None = None,
) -> dict[str, Any]:
    if skill_id.startswith('app:'):
        raise ValueError('随包技能由所属插件统一管理')
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


def _install_target(base: Path, skill_id: str) -> Path:
    # IDs are directory names, never paths. Apply Windows rules on every OS so
    # a package cannot become unsafe when copied to a different platform.
    if (not skill_id or skill_id in {".", ".."}
            or skill_id.endswith((".", " "))
            or re.search(r'[<>:"/\\|?*\x00-\x1f]', skill_id)
            or re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", skill_id)):
        raise ValueError("skill id must be a safe directory name")
    dest = base / skill_id
    if dest.is_symlink() or dest.resolve().parent != base.resolve():
        raise ValueError("skill installation target escapes the skills directory")
    return dest


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
            for entry in zf.infolist():
                parts = PurePosixPath(entry.filename).parts
                if (not parts or entry.filename.startswith("/")
                        or any(p in {".", ".."} or re.search(r'[<>:"\\|?*\x00-\x1f]', p) for p in parts)
                        or stat.S_ISLNK(entry.external_attr >> 16)):
                    raise ValueError("unsafe path or link in skill archive")
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
        if meta.id.startswith('app:'):
            raise ValueError('插件技能身份不能通过独立技能导入冒用')
        dest = _install_target(base, meta.id)
        # Finish copying before replacing an installed skill. Keep the old
        # directory until the final rename succeeds so failed updates retain it.
        stage = Path(tempfile.mkdtemp(prefix=".install-", dir=base))
        preserve_backup = False
        try:
            staged = stage / "new"
            backup = stage / "old"
            shutil.copytree(src_dir, staged)
            _install_target(base, meta.id)
            if dest.exists():
                dest.rename(backup)
            try:
                staged.rename(dest)
            except OSError:
                if backup.exists():
                    preserve_backup = True
                    try:
                        backup.rename(dest)
                    except OSError as exc:
                        raise OSError(f"技能更新及恢复失败，原技能保留在 {backup}") from exc
                    preserve_backup = False
                raise
        finally:
            if not preserve_backup:
                shutil.rmtree(stage)
        if (dest / "skill.yaml").is_file():
            return load_skill_yaml(dest / "skill.yaml")
        return load_skill_md(dest / "SKILL.md")


def delete_skill(skill_id: str, root: Path | None = None, config_path: Path | None = None) -> bool:
    if skill_id.startswith('app:'):
        raise ValueError('随包技能由所属插件统一管理')
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
    base = root or default_skills_root()
    if dest.is_symlink() or dest.resolve().parent != base.resolve():
        raise ValueError("skill deletion target escapes the skills directory")
    shutil.rmtree(dest)
    cfg = load_skills_config(config_path)
    if skill_id in (cfg.get("skills") or {}):
        del cfg["skills"][skill_id]
        save_skills_config(cfg, config_path)
    return True
