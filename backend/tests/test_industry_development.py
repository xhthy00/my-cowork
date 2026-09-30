import io
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI

from app.industry_apps.development import package_path, stage_development, collect_development
from app.industry_apps.lifecycle import Maintenance, runtime_entries
from app.industry_apps.loader import load_enabled_apps
from app.industry_apps.package import inspect_zip, install_zip
from test_industry_lifecycle import bundle, activate, APP


def test_development_requires_explicit_session(tmp_path, monkeypatch):
    raw = bundle('1.0.0')
    with pytest.raises(ValueError, match='开发会话'):
        stage_development(raw, inspect_zip(raw).sha256, tmp_path)
    monkeypatch.setenv('MY_COWORK_APP_DEV', '1')
    monkeypatch.setenv('MY_COWORK_DEV_APP_ID', 'cn.other.app')
    with pytest.raises(ValueError, match='身份'):
        stage_development(raw, inspect_zip(raw).sha256, tmp_path)


def test_same_version_reload_recovers_data_and_keeps_formal_rule(tmp_path, monkeypatch):
    monkeypatch.setenv('MY_COWORK_APP_DEV', '1')
    monkeypatch.setenv('MY_COWORK_DEV_APP_ID', APP)
    old = bundle('1.0.0')
    with_session = Maintenance(tmp_path)
    try:
        with_session.begin('develop', raw=old, sha256=inspect_zip(old).sha256)
        activate(with_session)
        first = runtime_entries(tmp_path)[0]
        assert package_path(tmp_path, APP, first).is_dir()
        data = tmp_path / 'data' / APP
        data.mkdir(parents=True, exist_ok=True)
        (data / 'record').write_text('keep')
        bad = bundle('1.0.0', register="(ctx.data_root / 'record').write_text('broken')\n    raise ValueError('bad reload')")
        with_session.begin('develop', raw=bad, sha256=inspect_zip(bad).sha256)
        candidate = with_session.prepare()
        monkeypatch.setenv('MY_COWORK_OPERATION_TOKEN', candidate['token'])
        # Do not import the preceding revision's Python modules in this process.
        import sys
        for key in list(sys.modules):
            if key.startswith('mcapp_cn_test_lifecycle'):
                del sys.modules[key]
        assert load_enabled_apps(FastAPI(), tmp_path)[0]['status'] == 'load_failed'
        monkeypatch.delenv('MY_COWORK_OPERATION_TOKEN')
        with_session.restore('bad reload')
        with_session.commit()
        assert (data / 'record').read_text() == 'keep'
        assert runtime_entries(tmp_path)[0]['dev_revision'] == first['dev_revision']
    finally:
        with_session.close()
        for key in list(sys.modules):
            if key.startswith('mcapp_cn_test_lifecycle'):
                del sys.modules[key]
    with pytest.raises(ValueError, match='同版本'):
        install_zip(old, inspect_zip(old).sha256, tmp_path)


def test_no_change_and_data_version_boundary(tmp_path, monkeypatch):
    monkeypatch.setenv('MY_COWORK_APP_DEV', '1')
    monkeypatch.setenv('MY_COWORK_DEV_APP_ID', APP)
    raw = bundle('1.0.0')
    session = Maintenance(tmp_path)
    try:
        session.begin('develop', raw=raw, sha256=inspect_zip(raw).sha256)
        activate(session)
        assert session.begin('develop', raw=raw, sha256=inspect_zip(raw).sha256)['unchanged']
        updated = bundle('1.0.1', schema=2)
        with pytest.raises(ValueError, match='package-test'):
            session.begin('develop', raw=updated, sha256=inspect_zip(updated).sha256)
        assert len(list((tmp_path / 'development' / APP).iterdir())) == 1
    finally:
        session.close()


def test_forged_revision_never_resolves_outside_managed_root(tmp_path, monkeypatch):
    monkeypatch.setenv('MY_COWORK_APP_DEV', '1')
    monkeypatch.setenv('MY_COWORK_DEV_APP_ID', APP)
    with pytest.raises(ValueError):
        package_path(tmp_path, APP, {'version': '1.0.0', 'dev_revision': '../elsewhere'})


def test_collect_retains_current_candidate_recovery_and_unfinished_operation(tmp_path, monkeypatch):
    from app.industry_apps import registry
    monkeypatch.setenv('MY_COWORK_APP_DEV', '1')
    monkeypatch.setenv('MY_COWORK_DEV_APP_ID', APP)
    revisions = [str(i) * 64 for i in range(1, 6)]
    for revision in revisions:
        (tmp_path / 'development' / APP / revision).mkdir(parents=True)
    registry.write(tmp_path, 'registry', {'apps': {APP: {
        'dev_revision': revisions[0], 'candidate': {'dev_revision': revisions[1]},
        'recovery': {'entry': {'dev_revision': revisions[2]}},
    }}})
    registry.write(tmp_path, 'operation', {'phase': 'recovery_required', 'old_entry': {'dev_revision': revisions[3]}})
    collect_development(tmp_path)
    assert sorted(p.name for p in (tmp_path / 'development' / APP).iterdir()) == revisions[:4]


def test_deliverable_collection_excludes_data_and_checks_before_publish(tmp_path):
    from app.industry_apps.packing import build_zip, publish
    source = tmp_path / 'source'
    source.mkdir()
    with zipfile.ZipFile(io.BytesIO(bundle())) as archive:
        archive.extractall(source)
    (source / '.env').write_text('secret')
    (source / 'frontend' / 'node_modules').mkdir()
    (source / 'frontend' / 'node_modules' / 'dependency').write_text('ignore')
    (source / 'frontend/dist/.vite').mkdir()
    (source / 'frontend/dist/.vite/cache.js').write_text('development cache')
    (source / 'backend' / 'mcapp_cn_test_lifecycle' / 'records.db').write_text('data')
    raw, inspection = build_zip(source)
    assert raw == build_zip(source)[0]
    assert not any(name.endswith('.db') or 'node_modules' in name or '.env' in name or '.vite' in name for name in inspection.files)
    out = tmp_path / 'result.zip'
    publish(source, out)
    with pytest.raises(FileExistsError):
        publish(source, out)
    (source / 'frontend/dist/index.html').unlink()
    with pytest.raises(ValueError):
        publish(source, tmp_path / 'invalid.zip')
    assert not (tmp_path / 'invalid.zip').exists()
