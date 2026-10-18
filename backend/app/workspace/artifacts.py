"""Host-verified deliverables, including existing files returned again in an answer."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from app.workspace.output_files import DELIVERABLE_EXT, SKIP_DIRS
from app.sandbox.path_guard import PathGuardError

_EXT = '|'.join(sorted(ext[1:] for ext in DELIVERABLE_EXT))
_ABSOLUTE = re.compile(
    r'(?:^|[\s`\'"(<：:])((?:file:///|/|~/|[A-Za-z]:[\\/])'
    r'[^\r\n`\'"<>|]*?\.(?:' + _EXT + r'))(?=$|[\s`\'"<>),，。;；\]])', re.I)
_QUOTED = re.compile(r'`([^`\r\n]+)`|\]\(<?([^\r\n]+?)>?\)(?=\s|$)', re.M)


def paths_in_answer(text: str) -> list[str]:
    """Candidates only: never treat model text as proof that a file exists."""
    body = re.sub(r'\\u([0-9a-fA-F]{4})', lambda match: chr(int(match[1], 16)), text or '')
    candidates = [match[1] for match in _ABSOLUTE.finditer(body)]
    candidates.extend(match[1] or match[2] for match in _QUOTED.finditer(body))
    return list(dict.fromkeys(candidates))


def paths_in_write_result(result) -> list[str]:
    if isinstance(result, str):
        try:
            return paths_in_write_result(json.loads(result))
        except (ValueError, TypeError):
            return [m[1].strip() for m in re.finditer(r'Wrote\s+\d+\s+characters\s+to\s+([^\r\n]+)', result, re.I)]
    if isinstance(result, dict):
        return [str(result[key]) for key in ('path', 'out_path', 'file_path', 'output_path') if result.get(key)]
    return []


def verified_artifact(raw: str, workspace: str, guard, app_scope=None) -> str | None:
    """Resolve virtual/relative paths and enforce the existing host file scope."""
    try:
        value = raw.strip().strip('`\'"<>')
        if value.startswith('file:'):
            url = urlsplit(value)
            if url.netloc not in ('', 'localhost'):
                return None
            value = unquote(url.path)
            if re.match(r'^/[A-Za-z]:[\\/]', value):
                value = value[1:]
        elif re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', value):
            return None
        if value.startswith('/workspace/'):
            target = Path(workspace) / value.removeprefix('/workspace/')
        else:
            target = Path(value).expanduser()
            if not target.is_absolute():
                target = Path(workspace) / target
        target = target.resolve()
        if target.suffix.lower() not in DELIVERABLE_EXT or target.name.startswith('.') or any(part in SKIP_DIRS for part in target.parts):
            return None
        if app_scope is not None:
            allowed = {str(Path(path).resolve()) for path in [*app_scope.artifacts, *app_scope.files.values()]}
            in_output = app_scope.output_dir and target.is_relative_to(Path(app_scope.output_dir).resolve())
            if str(target) not in allowed and not in_output:
                return None
        else:
            guard.check_path(str(target))
        return str(target) if target.is_file() else None
    except (OSError, ValueError, RuntimeError, PathGuardError):
        return None
