from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest
import yaml

from app.industry_apps.package import inspect_zip, install_zip, list_installed


APP = "cn.test.lifecycle"


def bundle(version="1.0.0", *, schema=1, migration="", health="", register=""):
    manifest = {
        "schema_version": schema, "id": APP, "name": "Lifecycle fixture",
        "version": version, "kind": "python-web", "backend": {"entry": "mcapp_cn_test_lifecycle:register"},
        "ui": {"entry": "frontend/dist/index.html"},
    }
    if schema == 2:
        manifest["data"] = {"version": 2, "upgrade_from": ["legacy"], "migration_entry": "mcapp_cn_test_lifecycle:migrate"}
        manifest["backend"]["health_entry"] = "mcapp_cn_test_lifecycle:check"
    code = (
        "from fastapi import APIRouter\nfrom app.industry_apps.sdk import AppContribution\n"
        "def register(ctx):\n    " + (register or "return AppContribution(router=APIRouter())") + "\n"
        "def migrate(ctx):\n    " + (migration or "pass") + "\n"
        "def check(ctx):\n    " + (health or "pass") + "\n"
    )
    files = {"mycowork-app.yaml": yaml.safe_dump(manifest).encode(),
             "backend/mcapp_cn_test_lifecycle/__init__.py": code.encode(),
             "frontend/dist/index.html": version.encode()}
    files["checksums.sha256"] = "".join(hashlib.sha256(v).hexdigest() + "  " + k + "\n" for k, v in files.items()).encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)
    return out.getvalue()


def stage(root, raw):
    return install_zip(raw, inspect_zip(raw).sha256, root)


def test_stage_does_not_activate_or_replace_running_version(tmp_path):
    stage(tmp_path, bundle())
    entry = list_installed(tmp_path)[0]
    assert entry.get("version") is None
    assert entry["candidate"]["version"] == "1.0.0"
    assert (tmp_path / "registry.db").exists()


def test_snapshot_restores_all_spaces_and_can_repeat_after_interruption(tmp_path):
    from app.industry_apps.snapshots import create_snapshot, restore_snapshot
    data = tmp_path / "data" / APP
    for space in ["local", "other"]:
        (data / space).mkdir(parents=True)
        with sqlite3.connect(data / space / "tasks.db") as db:
            db.execute("create table tasks(title text)")
            db.execute("insert into tasks values (?)", (space,))
        db.close()
    snap = create_snapshot(tmp_path, APP, "a" * 32)
    (data / "local" / "new.txt").write_text("new")
    restore_snapshot(tmp_path, APP, "b" * 32, snap)
    restore_snapshot(tmp_path, APP, "b" * 32, snap)
    assert not (data / "local" / "new.txt").exists()
    assert (tmp_path / "retained" / ("b" * 32) / "local" / "new.txt").read_text() == "new"
    for space in ["local", "other"]:
        with sqlite3.connect(data / space / "tasks.db") as db:
            assert db.execute("select title from tasks").fetchall() == [(space,)]
        db.close()


def test_corrupt_snapshot_never_replaces_current_data(tmp_path):
    from app.industry_apps.snapshots import create_snapshot, restore_snapshot
    data = tmp_path / "data" / APP
    data.mkdir(parents=True)
    (data / "record").write_text("old")
    snap = create_snapshot(tmp_path, APP, "c" * 32)
    (tmp_path / "recovery" / snap["id"] / "data" / "record").write_text("corrupt")
    (data / "record").write_text("current")
    with pytest.raises(ValueError, match="checksum"):
        restore_snapshot(tmp_path, APP, "d" * 32, snap)
    assert (data / "record").read_text() == "current"


def test_restore_retries_an_interrupted_preparation_copy(tmp_path, monkeypatch):
    from app.industry_apps import snapshots
    data = tmp_path / "data" / APP
    data.mkdir(parents=True)
    (data / "record").write_text("old")
    snap = snapshots.create_snapshot(tmp_path, APP, "a" * 32)
    (data / "record").write_text("current")
    real_copy = snapshots._copy
    def interrupted(source, target):
        target.mkdir()
        (target / "record").write_text("partial")
        raise OSError("interrupted copy")
    monkeypatch.setattr(snapshots, "_copy", interrupted)
    with pytest.raises(OSError, match="interrupted"):
        snapshots.restore_snapshot(tmp_path, APP, "b" * 32, snap)
    assert (data / "record").read_text() == "current"
    monkeypatch.setattr(snapshots, "_copy", real_copy)
    retained = snapshots.restore_snapshot(tmp_path, APP, "b" * 32, snap)
    assert (data / "record").read_text() == "old"
    assert (Path(retained) / "record").read_text() == "current"


def activate(session):
    """Use a fresh Python import process, as the real desktop does."""
    import os
    import subprocess
    import sys
    candidate = session.prepare()
    env = {**os.environ, "MY_COWORK_INDUSTRY_APPS_ROOT": str(session.root), "MY_COWORK_OPERATION_TOKEN": candidate["token"]}
    result = subprocess.run([sys.executable, "-c", "from fastapi import FastAPI; from app.industry_apps.loader import load_enabled_apps; import json; print(json.dumps(load_enabled_apps(FastAPI())))"], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    loaded = json.loads(result.stdout)
    if any(row["status"] != "ready" for row in loaded):
        raise RuntimeError(str(loaded))
    session.commit()


def test_migration_success_and_explicit_restore_keep_new_records(tmp_path):
    from app.industry_apps.lifecycle import Maintenance
    session = Maintenance(tmp_path)
    try:
        raw = bundle()
        session.begin("install", raw=raw, sha256=inspect_zip(raw).sha256)
        activate(session)
        data = tmp_path / "data" / APP
        data.mkdir(parents=True, exist_ok=True)
        (data / "record").write_text("original")
        updated = bundle("1.1.0", schema=2, migration="(ctx.data_root / 'record').write_text('migrated')")
        session.begin("install", raw=updated, sha256=inspect_zip(updated).sha256)
        assert list_installed(tmp_path)[0]["version"] == "1.0.0"
        activate(session)
        assert list_installed(tmp_path)[0]["data_version"] == 2
        assert (data / "record").read_text() == "migrated"
        (data / "record").write_text("new records")
        op = session.begin("rollback", APP)
        activate(session)
        assert (data / "record").read_text() == "original"
        assert (tmp_path / "retained" / op["id"] / "record").read_text() == "new records"
        assert list_installed(tmp_path)[0]["version"] == "1.0.0"
    finally:
        session.close()


def test_ordinary_startup_can_disable_failure_without_reverting_data(tmp_path):
    from app.industry_apps.lifecycle import Maintenance, runtime_entries
    session = Maintenance(tmp_path)
    try:
        raw = bundle()
        session.begin("install", raw=raw, sha256=inspect_zip(raw).sha256)
        activate(session)
        data = tmp_path / "data" / APP
        data.mkdir(parents=True, exist_ok=True)
        (data / "new-record").write_text("preserve committed data")
        session.begin("restart")
        session.prepare()
        candidate = session.disable_failed([{"id": APP, "error": "health failed"}])
        assert not runtime_entries(tmp_path, candidate["token"])[0]["enabled"]
        session.commit()
        assert (data / "new-record").read_text() == "preserve committed data"
        assert list_installed(tmp_path)[0]["status"] == "load_failed"
    finally:
        session.close()


def test_update_saved_without_model_remains_available_for_later_enable(tmp_path):
    from app.industry_apps.lifecycle import Maintenance
    session = Maintenance(tmp_path)
    try:
        raw = bundle()
        session.begin("install", raw=raw, sha256=inspect_zip(raw).sha256)
        activate(session)
        newer = bundle("1.0.1")
        session.begin("install", raw=newer, sha256=inspect_zip(newer).sha256)
        session.cancel(keep_candidate=True)
        entry = list_installed(tmp_path)[0]
        assert entry["version"] == "1.0.0"
        assert entry["candidate"]["version"] == "1.0.1"
        assert session.begin("enable", APP)["target"]["version"] == "1.0.1"
    finally:
        session.close()


def test_failed_migration_restores_data_before_old_code_can_load(tmp_path):
    from app.industry_apps.lifecycle import Maintenance, runtime_entries
    session = Maintenance(tmp_path)
    try:
        raw = bundle()
        session.begin("install", raw=raw, sha256=inspect_zip(raw).sha256)
        activate(session)
        data = tmp_path / "data" / APP
        data.mkdir(parents=True, exist_ok=True)
        (data / "record").write_text("original")
        raw = bundle("1.1.0", schema=2, migration="(ctx.data_root / 'record').write_text('partial'); raise RuntimeError('intentional failure')")
        session.begin("install", raw=raw, sha256=inspect_zip(raw).sha256)
        with pytest.raises(ValueError, match="intentional failure"):
            session.prepare()
        assert (data / "record").read_text() == "partial"
        with pytest.raises(RuntimeError, match="未完成"):
            runtime_entries(tmp_path)
        session.restore("migration failed")
        assert (data / "record").read_text() == "original"
        session.commit()
        assert list_installed(tmp_path)[0]["version"] == "1.0.0"
    finally:
        session.close()


def test_snapshot_and_recovery_cannot_run_while_backend_holds_lock(tmp_path):
    from app.industry_apps.lifecycle import Maintenance
    from app.industry_apps.locks import FileLock
    session = Maintenance(tmp_path)
    try:
        raw = bundle()
        session.begin("install", raw=raw, sha256=inspect_zip(raw).sha256)
        with FileLock(tmp_path, "running"):
            with pytest.raises(RuntimeError, match="另一进程"):
                session.prepare()
        assert not (tmp_path / "recovery").exists()
    finally:
        session.close()


def test_legacy_registry_import_is_once_and_pending_update_uses_known_old_version(tmp_path):
    from app.industry_apps import registry
    raw = bundle()
    stage(tmp_path, raw)
    first = inspect_zip(raw).manifest.model_dump()
    second = {**first, "version": "1.1.0"}
    (tmp_path / "registry.db").unlink()
    (tmp_path / "registry.json").write_text(json.dumps({"schema_version": 1, "apps": {APP: {"manifest": second, "version": "1.1.0", "previous_version": "1.0.0", "enabled": True, "status": "pending_restart"}}}))
    entry = list_installed(tmp_path)[0]
    assert entry["version"] == "1.0.0"
    assert entry["candidate"]["version"] == "1.1.0"
    assert "recovery" not in entry
    (tmp_path / "registry.json").write_text("invalid now")
    assert registry.read(tmp_path)["apps"][APP]["version"] == "1.0.0"


@pytest.mark.parametrize("failure", ["register", "health"])
def test_registration_and_health_failure_restore_real_records(tmp_path, failure):
    from app.industry_apps.lifecycle import Maintenance
    session = Maintenance(tmp_path)
    try:
        original = bundle()
        session.begin("install", raw=original, sha256=inspect_zip(original).sha256)
        activate(session)
        data = tmp_path / "data" / APP
        data.mkdir(parents=True)
        (data / "record").write_text("original")
        options = {"register": "(ctx.data_root / 'record').write_text('broken'); raise RuntimeError('bad register')"} if failure == "register" else {"health": "raise RuntimeError('bad health')"}
        updated = bundle("1.1.0", schema=2, **options)
        session.begin("install", raw=updated, sha256=inspect_zip(updated).sha256)
        with pytest.raises(RuntimeError, match="load_failed"):
            activate(session)
        session.restore("load failed")
        assert (data / "record").read_text() == "original"
        session.commit()
    finally:
        session.close()


def test_directory_swap_resumes_after_old_data_was_renamed(tmp_path, monkeypatch):
    from app.industry_apps import snapshots
    data = tmp_path / "data" / APP
    data.mkdir(parents=True)
    (data / "record").write_text("before")
    snap = snapshots.create_snapshot(tmp_path, APP, "a" * 32)
    (data / "record").write_text("after")
    replace = snapshots.os.replace
    def interrupted(source, target):
        if Path(source).name.startswith(".restore-"):
            raise OSError("simulated interruption between directory renames")
        return replace(source, target)
    with monkeypatch.context() as scoped:
        scoped.setattr(snapshots.os, "replace", interrupted)
        with pytest.raises(OSError, match="interruption"):
            snapshots.restore_snapshot(tmp_path, APP, "b" * 32, snap)
    snapshots.restore_snapshot(tmp_path, APP, "b" * 32, snap)
    assert (data / "record").read_text() == "before"
    assert (tmp_path / "retained" / ("b" * 32) / "record").read_text() == "after"


def test_restart_recovers_uncommitted_migration_but_never_committed_data(tmp_path):
    from app.industry_apps.lifecycle import Maintenance
    first = Maintenance(tmp_path)
    raw = bundle()
    first.begin("install", raw=raw, sha256=inspect_zip(raw).sha256)
    activate(first)
    data = tmp_path / "data" / APP
    data.mkdir(parents=True)
    (data / "record").write_text("before")
    updated = bundle("1.1.0", schema=2, migration="(ctx.data_root / 'record').write_text('migrated')")
    first.begin("install", raw=updated, sha256=inspect_zip(updated).sha256)
    first.prepare()
    first.close()  # Simulate loss of the desktop after migration, before commit.
    second = Maintenance(tmp_path)
    try:
        second.restore("interrupted")
        assert (data / "record").read_text() == "before"
        second.commit()
        second.begin("install", raw=updated, sha256=inspect_zip(updated).sha256)
        activate(second)
        (data / "record").write_text("new user records")
        assert second.restore("later crash") is None
        assert (data / "record").read_text() == "new user records"
    finally:
        second.close()


def test_failed_restore_can_quarantine_without_losing_recovery_point(tmp_path, monkeypatch):
    from app.industry_apps import lifecycle
    session = lifecycle.Maintenance(tmp_path)
    try:
        raw = bundle()
        session.begin("install", raw=raw, sha256=inspect_zip(raw).sha256)
        activate(session)
        data = tmp_path / "data" / APP
        data.mkdir(parents=True)
        (data / "record").write_text("old")
        raw = bundle("1.1.0", schema=2)
        session.begin("install", raw=raw, sha256=inspect_zip(raw).sha256)
        session.prepare()
        with monkeypatch.context() as scoped:
            scoped.setattr(lifecycle, "restore_snapshot", lambda *a: (_ for _ in ()).throw(OSError("locked")))
            with pytest.raises(OSError):
                session.restore()
        session.quarantine()
        public = list_installed(tmp_path)[0]
        assert public["enabled"] is False and public["needs_recovery"] is True
        assert "recovery_operation" not in public
        session.retry(APP)
        session.restore()
        session.commit()
        assert (data / "record").read_text() == "old"
    finally:
        session.close()
