"""Minimal skill loader: skill.yaml + Eigent-style SKILL.md."""

from __future__ import annotations

import re
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


def repo_root() -> Path:
    # backend/app/skills/__init__.py → my-cowork/
    return Path(__file__).resolve().parents[3]


def default_user_skills_root() -> Path:
    return repo_root() / "skills"


def default_example_skills_root() -> Path:
    return repo_root() / "resources" / "example-skills"


def load_skill_yaml(path: Path, *, is_example: bool = False) -> SkillMeta:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
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
        meta = load_skill_yaml(path, is_example=is_example)
        if meta.id in seen:
            continue
        seen.add(meta.id)
        out.append(meta)
    for path in sorted(base.glob("*/SKILL.md")):
        if path.parent.name.startswith("_"):
            continue
        if (path.parent / "skill.yaml").is_file():
            continue
        meta = load_skill_md(path, is_example=is_example)
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
    user = Path.home() / ".my-cowork" / "skills"
    if user.resolve() != default_user.resolve():
        roots.append((user, False))
    examples = default_example_skills_root()
    if examples.is_dir():
        roots.append((examples, True))
    return roots


def discover_skills(root: Path | None = None) -> list[SkillMeta]:
    """Load ``*/skill.yaml`` and ``*/SKILL.md`` under user + example skill roots."""
    seen: set[str] = set()
    skills: list[SkillMeta] = []
    for base, is_example in _skill_roots(root):
        _scan_root(base, is_example=is_example, seen=seen, out=skills)
    return skills


def find_skill(skill_id: str, root: Path | None = None) -> SkillMeta | None:
    needle = (skill_id or "").strip()
    for skill in discover_skills(root):
        if skill.id == needle or skill.name == needle:
            return skill
    return None


def format_loaded_skill(meta: SkillMeta) -> str:
    """Eigent/CAMEL-style load_skill return body."""
    base = meta.base_dir or (meta.path.parent if meta.path else None)
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
