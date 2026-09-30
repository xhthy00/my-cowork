"""Minimal skill loader: skill.yaml + Eigent-style SKILL.md."""

from __future__ import annotations

import os
import logging
import re
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_FRONTMATTER_RE = re.compile(r"^---\s*\n([\s\S]*?)\n---\s*\n?", re.MULTILINE)


@dataclass
class SkillMeta:
    id: str
    name: str = ""
    description: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    schedule: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    prompt: str = ""
    path: Path | None = None
    base_dir: Path | None = None
    is_example: bool = False
    app_origin: dict[str, str] | None = None
    available: bool = True


_bundled: ContextVar[dict[str, SkillMeta]] = ContextVar('bundled_skills', default={})
task_skill_selection: ContextVar[dict[str, SkillMeta] | None] = ContextVar('task_skill_selection', default=None)


@contextmanager
def bundled_skill_scope(skills: dict[str, SkillMeta], *, selected: dict[str, SkillMeta] | None = None):
    token = _bundled.set(skills)
    selection_token = task_skill_selection.set(selected)
    try:
        yield
    finally:
        task_skill_selection.reset(selection_token)
        _bundled.reset(token)


def repo_root() -> Path:
    # backend/app/skills/__init__.py → my-cowork/
    return Path(__file__).resolve().parents[3]


def default_user_skills_root() -> Path:
    custom = os.environ.get("MY_COWORK_SKILLS_ROOT")
    if custom:
        return Path(custom).expanduser().resolve()
    data = os.environ.get("MY_COWORK_DATA_DIR")
    return (Path(data).expanduser() if data else Path.home() / ".my-cowork") / "skills"


def legacy_user_skills_roots() -> list[Path]:
    target = default_user_skills_root().resolve()
    candidates = [repo_root() / "skills", Path.home() / ".my-cowork" / "skills"]
    if getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
        candidates.extend([executable_dir / "skills", executable_dir.parent / "skills"])
    return list(dict.fromkeys(p for p in candidates if p.resolve() != target))


def default_example_skills_root() -> Path:
    """Bundled example-skills directory (dev repo or packaged extraResources).

    Packaged layout puts examples at ``{resourcesPath}/resources/example-skills``,
    not next to the PyInstaller runtime. ``repo_root()`` in a frozen onedir is
    ``python_runtime/``, so a naive ``repo_root()/resources/example-skills``
    misses every built-in skill.
    """
    env = (os.environ.get("MY_COWORK_EXAMPLE_SKILLS") or "").strip()
    if env:
        return Path(env)
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        for candidate in (
            exe_dir.parent / "resources" / "example-skills",
            exe_dir / "resources" / "example-skills",
        ):
            if candidate.is_dir():
                return candidate
    return repo_root() / "resources" / "example-skills"


def _validate_metadata(data: Any) -> None:
    if not isinstance(data, dict):
        raise ValueError("技能元数据必须是键值映射")
    if data.get("params") is not None and not isinstance(data["params"], dict):
        raise ValueError("技能 params 必须是键值映射")
    if data.get("allowed_tools") is not None and not isinstance(data["allowed_tools"], list):
        raise ValueError("技能 allowed_tools 必须是列表")


def load_skill_yaml(path: Path, *, is_example: bool = False) -> SkillMeta:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError("技能 YAML 语法错误") from exc
    if data is None:
        data = {}
    _validate_metadata(data)
    skill_id = str(data.get("id") or path.parent.name)
    return SkillMeta(
        id=skill_id,
        name=str(data.get("name") or skill_id),
        description=str(data.get("description") or ""),
        allowed_tools=list(data.get("allowed_tools") or []),
        schedule=data.get("schedule"),
        params=dict(data.get("params") or {}),
        prompt=str(data.get("prompt") or ""),
        path=path,
        base_dir=path.parent,
        is_example=is_example,
    )


def load_skill_md(path: Path, *, is_example: bool = False) -> SkillMeta:
    """Parse Eigent-style SKILL.md (YAML frontmatter + markdown body)."""
    raw = path.read_text(encoding="utf-8")
    fm: dict[str, Any] = {}
    body = raw
    m = _FRONTMATTER_RE.match(raw)
    if m:
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except Exception:
            fm = {}
        if not isinstance(fm, dict):
            fm = {}
        body = raw[m.end() :]
    skill_id = str(fm.get("name") or path.parent.name).strip() or path.parent.name
    _validate_metadata(fm)
    return SkillMeta(
        id=skill_id,
        name=skill_id,
        description=str(fm.get("description") or "").strip(),
        allowed_tools=list(fm.get("allowed_tools") or []),
        schedule=fm.get("schedule"),
        params=dict(fm.get("params") or {}),
        prompt=body.strip(),
        path=path,
        base_dir=path.parent,
        is_example=is_example,
    )


def _scan_root(base: Path, *, is_example: bool, seen: set[str], out: list[SkillMeta]) -> None:
    if not base.is_dir():
        return
    for path in sorted(base.glob("*/skill.yaml")):
        if path.parent.name.startswith("_"):
            continue
        try:
            meta = load_skill_yaml(path, is_example=is_example)
        except (OSError, ValueError) as exc:
            logging.getLogger(__name__).warning("Skipping unreadable skill %s: %s", path, exc)
            continue
        if meta.id in seen:
            continue
        seen.add(meta.id)
        out.append(meta)
    for path in sorted(base.glob("*/SKILL.md")):
        if path.parent.name.startswith("_"):
            continue
        if (path.parent / "skill.yaml").is_file():
            continue
        try:
            meta = load_skill_md(path, is_example=is_example)
        except (OSError, ValueError) as exc:
            logging.getLogger(__name__).warning("Skipping unreadable skill %s: %s", path, exc)
            continue
        if meta.id in seen:
            continue
        seen.add(meta.id)
        out.append(meta)


def _skill_roots(root: Path | None = None) -> list[tuple[Path, bool]]:
    """(path, is_example) discovery roots. User skills override examples on id clash.

    Isolated custom roots (tests / tmp dirs) scan only that path. The default
    user skills directory also pulls in bundled ``resources/example-skills``.
    """
    default_user = default_user_skills_root()
    if root is not None and root.resolve() != default_user.resolve():
        return [(root, False)]

    roots: list[tuple[Path, bool]] = [(default_user, False)]
    # Keep failed/unstarted migrations usable. Once migration is complete,
    # preserved backups must not resurrect skills deleted in the new location.
    if not (default_user / ".migration-v1.json").is_file():
        roots.extend((p, False) for p in legacy_user_skills_roots())
    examples = default_example_skills_root()
    if examples.is_dir():
        roots.append((examples, True))
    return roots


def discover_skills(root: Path | None = None, *, bundled: dict[str, SkillMeta] | None = None) -> list[SkillMeta]:
    """Load ``*/skill.yaml`` and ``*/SKILL.md`` under user + example skill roots."""
    seen: set[str] = set()
    skills: list[SkillMeta] = []
    for base, is_example in _skill_roots(root):
        _scan_root(base, is_example=is_example, seen=seen, out=skills)
    # The app namespace cannot be shadowed by user files or display names.
    return [s for s in skills if not s.id.startswith('app:')] + list((_bundled.get() if bundled is None else bundled).values())


def find_skill(skill_id: str, root: Path | None = None) -> SkillMeta | None:
    needle = (skill_id or "").strip()
    if needle.startswith('app:'):
        meta = _bundled.get().get(needle)
        return meta if meta and meta.available else None
    for skill in discover_skills(root):
        if not skill.app_origin and (skill.id == needle or skill.name == needle):
            return skill
    return None


def format_loaded_skill(meta: SkillMeta) -> str:
    """Eigent/CAMEL-style load_skill return body."""
    base = meta.base_dir or (meta.path.parent if meta.path else None)
    if meta.app_origin:
        return (
            f'## Skill: {meta.name}\nID: {meta.id}\n'
            f'Plugin: {meta.app_origin["name"]} {meta.app_origin["version"]}\n'
            'Read referenced text using read_skill_resource(name=the full skill ID, path=relative path).\n'
            f'{meta.prompt}\n'
        )
    files_block = "(none)"
    if base and base.is_dir():
        entries: list[str] = []
        for item in sorted(base.iterdir()):
            if item.name.startswith("."):
                continue
            suffix = "/" if item.is_dir() else ""
            entries.append(f"  - {item.name}{suffix}")
        if entries:
            files_block = "\n".join(entries)
    return (
        f"## Skill: {meta.name or meta.id}\n\n"
        f"**Base directory**: {base or '(unknown)'}\n\n"
        f"**Available files**:\n{files_block}\n\n"
        f"{meta.prompt or '(empty skill body)'}\n"
    )
