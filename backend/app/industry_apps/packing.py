"""Collect only deliverable files; validate the exact deterministic ZIP."""
from __future__ import annotations
import hashlib
import io
import os
import zipfile
from pathlib import Path
import yaml
from .package import AppManifest, inspect_zip
from .snapshots import checked_path

EXCLUDED_DIRS = {'node_modules', '__pycache__', '.git', '.cache', '.vite', '.vite-temp', '.venv', 'tests'}
EXCLUDED_SUFFIXES = {'.pyc', '.db', '.sqlite', '.sqlite3', '.log', '.pem', '.key'}


def build_zip(source: Path):
    source = checked_path(source)
    manifest = AppManifest.model_validate(yaml.safe_load(checked_path(source / 'mycowork-app.yaml').read_text(encoding='utf-8')))
    namespace = f'mcapp_{manifest.id.replace(".", "_")}'
    roots = [source / 'backend' / namespace, source / 'frontend' / 'dist', *(source / directory for directory in manifest.skills)]
    files = {'mycowork-app.yaml': checked_path(source / 'mycowork-app.yaml').read_bytes()}
    for root in roots:
        checked_path(root)
        if not root.is_dir():
            raise ValueError(f'缺少交付目录 {root.relative_to(source)}；请先构建前端')
        for directory, dirs, names in os.walk(root, followlinks=False):
            for name in dirs:
                if name not in EXCLUDED_DIRS:
                    checked_path(Path(directory) / name)
            dirs[:] = [name for name in dirs if name not in EXCLUDED_DIRS]
            for name in names:
                if name.startswith('.env') or name in {'credentials.json', 'checksums.sha256'} or Path(name).suffix.lower() in EXCLUDED_SUFFIXES:
                    continue
                file = checked_path(Path(directory) / name)
                files[file.relative_to(source).as_posix()] = file.read_bytes()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        checksums = [hashlib.sha256(content).hexdigest() + '  ' + name for name, content in sorted(files.items())]
        files['checksums.sha256'] = ('\n'.join(checksums) + '\n').encode()
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    raw = stream.getvalue()
    return raw, inspect_zip(raw)


def publish(source: Path, output: Path, *, replace=False):
    source, output = checked_path(source), checked_path(output)
    if output.is_relative_to(source):
        raise ValueError('output ZIP must be outside the source directory')
    raw, inspection = build_zip(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    import tempfile
    with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as temporary:
        temporary.write(raw); temporary.flush(); os.fsync(temporary.fileno())
        name = temporary.name
    try:
        if replace:
            os.replace(name, output)
        else:
            # Atomic, exclusive publication on the same filesystem.
            os.link(name, output)
    finally:
        Path(name).unlink(missing_ok=True)
    return inspection
