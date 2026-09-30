"""One transactional registry; JSON is imported once, never written again."""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import yaml


@contextmanager
def transaction(root: Path):
    from .snapshots import checked_path
    checked_path(root)
    root.mkdir(parents=True, exist_ok=True)
    checked_path(root / "registry.db")
    db = sqlite3.connect(root / "registry.db", timeout=10)
    try:
        db.execute("PRAGMA synchronous=FULL")
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        if db.execute("SELECT 1 FROM state WHERE key='registry'").fetchone() is None:
            value = _import_json(root)
            db.execute("INSERT INTO state VALUES ('registry', ?)", (json.dumps(value),))
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def _import_json(root):
    from .package import AppManifest
    path = root / "registry.json"
    if not path.exists():
        return {"schema_version": 2, "apps": {}}
    from .snapshots import checked_path
    checked_path(path)
    old = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(old, dict) or not isinstance(old.get("apps"), dict):
        raise ValueError("application registry is invalid")
    for app_id, entry in old["apps"].items():
        manifest = AppManifest.model_validate(entry["manifest"])
        if manifest.id != app_id or manifest.version != entry["version"]:
            raise ValueError("legacy registry identity mismatch")
        pending = entry.get("status") == "pending_restart"
        entry["data_version"] = "legacy"
        entry["status"] = "pending_activation" if entry.get("enabled") else "disabled"
        if not checked_path(root / "packages" / app_id / entry["version"]).is_dir():
            entry.update(status="recovery_required", enabled=False, error="已安装版本的文件缺失")
        if entry.get("previous_version"):
            previous = str(entry["previous_version"])
            if not re.fullmatch(r"\d+\.\d+\.\d+", previous):
                raise ValueError("invalid previous version")
            # Old pending_restart may already have modified data. Never invent
            # a data version or a recovery point for an ambiguous installation.
            if pending:
                previous_file = checked_path(root / "packages" / app_id / previous / "mycowork-app.yaml")
                if previous_file.is_file():
                    prior = AppManifest.model_validate(yaml.safe_load(previous_file.read_text(encoding="utf-8")))
                    if prior.id != app_id or prior.version != previous:
                        raise ValueError("legacy previous version mismatch")
                    entry["candidate"] = {"manifest": entry["manifest"], "version": entry["version"], "sha256": entry.get("sha256")}
                    entry.update(version=previous, manifest=prior.model_dump(), status="pending_activation", enabled=True)
                else:
                    entry.update(enabled=False, status="recovery_required", error="旧版缺失；无法确认历史更新状态")
        elif pending:
            entry["candidate"] = {"manifest": entry["manifest"], "version": entry["version"], "sha256": entry.get("sha256")}
            entry.update(version=None, enabled=False, status="pending_activation")
        entry.pop("previous_version", None)
    old["schema_version"] = 2
    return old


def read(root: Path, key="registry", default=None):
    with transaction(root) as db:
        row = db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default


def write(root: Path, key: str, value):
    with transaction(root) as db:
        put(db, key, value)


def put(db, key, value):
    db.execute("INSERT INTO state VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value, ensure_ascii=False)))


def commit_operation(root, registry, operation):
    with transaction(root) as db:
        put(db, "registry", registry)
        put(db, "operation", operation)
