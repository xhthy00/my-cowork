"""Immutable developer revisions in the existing lifecycle registry."""
from __future__ import annotations

import io
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from . import registry
from .package import inspect_zip
from .snapshots import managed


def package_path(root, app_id, entry):
    revision = entry.get('dev_revision')
    if not revision:
        return managed(root, 'packages', app_id, entry['version'])
    if os.environ.get('MY_COWORK_APP_DEV') != '1' or os.environ.get('MY_COWORK_DEV_APP_ID') != app_id:
        raise ValueError('开发源码只可在对应开发会话加载')
    if not re.fullmatch(r'[0-9a-f]{64}', revision):
        raise ValueError('invalid development revision')
    return managed(root, 'development', app_id, revision)


def stage_development(raw, expected_sha256, root):
    if os.environ.get('MY_COWORK_APP_DEV') != '1':
        raise ValueError('需要显式开发会话')
    inspection = inspect_zip(raw)
    manifest = inspection.manifest
    if os.environ.get('MY_COWORK_DEV_APP_ID') != manifest.id:
        raise ValueError('开发插件身份不一致')
    if inspection.sha256 != expected_sha256:
        raise ValueError('开发内容在检查后变化')
    state = registry.read(root)
    old = state['apps'].get(manifest.id, {})
    if old.get('recovery_operation'):
        raise ValueError('请先恢复未完成的数据操作')
    if old.get('version') and (not old.get('dev_revision') or old.get('data_version') != (manifest.data.version or 'legacy')):
        raise ValueError('数据格式变化或正式包切换需使用 package-test')
    candidate = {'manifest': manifest.model_dump(), 'version': manifest.version,
                 'sha256': inspection.sha256, 'dev_revision': inspection.sha256}
    destination = package_path(root, manifest.id, candidate)
    if old.get('dev_revision') == inspection.sha256 and old.get('enabled') and not old.get('candidate'):
        return {'id': manifest.id, 'unchanged': True}
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix='.stage-', dir=destination.parent))
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                for name in inspection.files:
                    target = stage / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open('wb') as output:
                        output.write(archive.read(name))
                        output.flush()
                        os.fsync(output.fileno())
            os.replace(stage, destination)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    entry = dict(old) if old else {'version': None, 'enabled': False, 'data_version': 'legacy', 'manifest': manifest.model_dump()}
    entry['candidate'] = candidate
    state['apps'][manifest.id] = entry
    registry.write(root, 'registry', state)
    return {'id': manifest.id, 'unchanged': False}


def collect_development(root):
    """Caller holds operation and running locks; retain every recovery reference."""
    state = registry.read(root)
    op = registry.read(root, 'operation')
    referenced = set()

    def retain(value):
        if isinstance(value, dict):
            if value.get('dev_revision'):
                referenced.add(value['dev_revision'])
            for nested in value.values():
                retain(nested)
        elif isinstance(value, list):
            for nested in value:
                retain(nested)

    retain(state)
    if op and op['phase'] not in {'committed', 'restored', 'cancelled'}:
        retain(op)
    app_id = os.environ.get('MY_COWORK_DEV_APP_ID', '')
    if os.environ.get('MY_COWORK_APP_DEV') != '1' or not re.fullmatch(r'[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)+', app_id):
        return
    directory = managed(root, 'development', app_id)
    if directory.exists():
        for child in directory.iterdir():
            if re.fullmatch(r'[0-9a-f]{64}', child.name) and child.name not in referenced:
                shutil.rmtree(managed(root, 'development', app_id, child.name))
