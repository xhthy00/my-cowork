"""Text-only package skill validation and bounded resource access."""
from pathlib import Path, PurePosixPath
import re
import stat

import yaml

from app.skills import SkillMeta, _FRONTMATTER_RE

MAX_SKILL_BYTES = 64 * 1024
MAX_SKILL_CHARS = 16000
MAX_TASK_SKILL_CHARS = 64000
MAX_RESOURCE_BYTES = 64 * 1024
SKILL_DIRECTORY = re.compile(r'^skills/[a-z][a-z0-9_-]{0,63}$')


def validate_skill_paths(paths: list[str]) -> None:
    if len(paths) > 32 or len(paths) != len(set(paths)):
        raise ValueError('skill declarations must be unique (maximum 32)')
    if any(not SKILL_DIRECTORY.fullmatch(path) for path in paths):
        raise ValueError('skill path must be skills/<lowercase-local-id>')


def parse_package_skill(raw: bytes, filename: str, manifest: dict, *, base_dir: Path | None = None, available: bool = True) -> SkillMeta:
    if len(raw) > MAX_SKILL_BYTES:
        raise ValueError('skill entry exceeds 64 KiB')
    text = raw.decode('utf-8-sig')
    if filename.endswith('SKILL.md'):
        match = _FRONTMATTER_RE.match(text)
        if not match:
            raise ValueError('skill SKILL.md requires YAML frontmatter')
        meta = yaml.safe_load(match.group(1))
        prompt = text[match.end():].strip()
    else:
        meta = yaml.safe_load(text)
        prompt = meta.get('prompt') if isinstance(meta, dict) else None
    if not isinstance(meta, dict):
        raise ValueError('skill metadata must be an object')
    name, description = meta.get('name'), meta.get('description', '')
    if not isinstance(name, str) or not name.strip() or len(name) > 100 or not isinstance(description, str) or len(description) > 1000:
        raise ValueError('skill name/description must be bounded text')
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_SKILL_CHARS:
        raise ValueError('skill body must contain 1–16000 characters; put long text in references')
    if meta.get('schedule') is not None:
        raise ValueError('skill schedules are not supported in application packages')
    allowed = meta.get('allowed_tools', [])
    if not isinstance(allowed, list) or any(not isinstance(value, str) for value in allowed) or not isinstance(meta.get('params', {}), dict):
        raise ValueError('skill allowed_tools/params metadata is invalid')
    local_id = PurePosixPath(filename).parent.name
    return SkillMeta(
        id=f'app:{manifest["id"]}:{local_id}', name=name.strip(), description=description,
        prompt=prompt.strip(), base_dir=base_dir,
        path=base_dir / PurePosixPath(filename).name if base_dir else None,
        app_origin={'id': manifest['id'], 'name': manifest['name'], 'version': manifest['version']},
        available=available,
    )


def safe_skill_path(base: Path, relative: str) -> Path:
    parts = PurePosixPath(relative).parts
    if not parts or relative.startswith('/') or '\\' in relative or ':' in relative or any(p in {'.', '..'} for p in relative.split('/')):
        raise ValueError('skill resource must use a relative path inside the skill')
    target = base.joinpath(*parts)
    # Reject junctions as well as symbolic links on Windows, including ancestors.
    for item in (target, *target.parents):
        info = item.lstat()
        if item.is_symlink() or getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0):
            raise ValueError('skill links are not allowed')
    if not target.resolve().is_relative_to(base.resolve()) or not target.is_file():
        raise ValueError('skill resource is missing or outside its directory')
    return target


def load_package_skills(manifest: dict, package: Path, *, available: bool = True) -> dict[str, SkillMeta]:
    declarations = manifest.get('skills', [])
    validate_skill_paths(declarations)
    result = {}
    for directory in declarations:
        entries = [name for name in ('SKILL.md', 'skill.yaml') if (package / directory / name).is_file()]
        if len(entries) != 1:
            raise ValueError(f'skill {directory} requires exactly one entry')
        path = safe_skill_path(package, f'{directory}/{entries[0]}')
        with path.open('rb') as stream:
            raw = stream.read(MAX_SKILL_BYTES + 1)
        meta = parse_package_skill(raw, f'{directory}/{entries[0]}', manifest, base_dir=path.parent, available=available)
        result[meta.id] = meta
    return result


def read_skill_resource(meta: SkillMeta, relative: str) -> str:
    if not meta.available or not meta.base_dir:
        raise ValueError('技能不可用')
    path = safe_skill_path(meta.base_dir, relative)
    if path.suffix.lower() not in {'.md', '.txt', '.csv', '.json', '.yaml', '.yml'}:
        raise ValueError('仅支持技能目录内的 UTF-8 文本资料')
    with path.open('rb') as stream:
        raw = stream.read(MAX_RESOURCE_BYTES + 1)
    if len(raw) > MAX_RESOURCE_BYTES:
        raise ValueError('技能资料超过 64 KiB，请拆分资料')
    return raw.decode('utf-8-sig')
