"""Offline, verified directory snapshots. Call only while holding the run lock."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def checked_path(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError(f"linked paths are unsupported: {part}")
        if not stat.S_ISDIR(info.st_mode) and (not stat.S_ISREG(info.st_mode) or info.st_nlink > 1):
            raise ValueError(f"unsupported file: {part}")
    return path


def managed(root: Path, *parts: str) -> Path:
    base = checked_path(root)
    path = checked_path(base.joinpath(*parts))
    if not path.is_relative_to(base) or path == base:
        raise ValueError("path is outside the application root")
    return path


def inventory(path):
    if not path.exists():
        return {}
    result = {}
    for item in sorted(path.rglob("*")):
        checked_path(item)
        if item.is_file():
            with item.open("rb") as stream:
                result[item.relative_to(path).as_posix()] = hashlib.file_digest(stream, "sha256").hexdigest()
    return result


def _copy(source, target):
    inventory(source)  # Reject links before copying any bytes.
    size = sum(p.stat().st_size for p in source.rglob("*") if p.is_file()) if source.exists() else 0
    if shutil.disk_usage(target.parent).free < size * 2 + 1024 * 1024:
        raise ValueError("磁盘空间不足，无法保存恢复点")
    if source.exists():
        shutil.copytree(source, target)
    else:
        target.mkdir()
    for p in target.rglob("*"):
        if p.is_file():
            with p.open("r+b") as f:
                os.fsync(f.fileno())


def _sqlite_check(data, temp_parent):
    # Opening SQLite can recover WAL/journal files; do that only on a scratch
    # copy, never on source data or the immutable recovery point.
    with tempfile.TemporaryDirectory(prefix=".verify-", dir=temp_parent) as scratch:
        copied = Path(scratch) / "data"
        shutil.copytree(data, copied)
        for file in copied.rglob("*"):
            if not file.is_file():
                continue
            with file.open("rb") as f:
                sqlite = f.read(16) == b"SQLite format 3\x00"
            if sqlite:
                db = sqlite3.connect(file)
                try:
                    if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                        raise ValueError(f"SQLite verification failed: {file.name}")
                finally:
                    db.close()


def create_snapshot(root: Path, app_id: str, snapshot_id: str):
    if not re.fullmatch(r"[a-f0-9]{32}", snapshot_id):
        raise ValueError("invalid snapshot id")
    source = managed(root, "data", app_id)
    destination = managed(root, "recovery", snapshot_id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        info = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
        verify_snapshot(root, info)
        return info
    stage = Path(tempfile.mkdtemp(prefix=".snapshot-", dir=destination.parent))
    try:
        _copy(source, stage / "data")
        files = inventory(stage / "data")
        if files != inventory(source):
            raise ValueError("data changed while creating snapshot")
        _sqlite_check(stage / "data", stage)
        info = {"id": snapshot_id, "app_id": app_id, "exists": source.exists(), "files": files,
                "created_at": datetime.now(timezone.utc).isoformat()}
        with (stage / "manifest.json").open("w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(stage, destination)
        return info
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def verify_snapshot(root, info):
    if not re.fullmatch(r"[a-f0-9]{32}", info["id"]):
        raise ValueError("invalid snapshot id")
    source = managed(root, "recovery", info["id"], "data")
    if not source.is_dir() or inventory(source) != info["files"]:
        raise ValueError("snapshot checksum verification failed")
    return source


def restore_snapshot(root: Path, app_id: str, operation_id: str, info):
    if info["app_id"] != app_id or not re.fullmatch(r"[a-f0-9]{32}", operation_id):
        raise ValueError("snapshot identity mismatch")
    source = verify_snapshot(root, info)
    data = managed(root, "data", app_id)
    retained = managed(root, "retained", operation_id)
    journal = managed(root, "retained", operation_id + ".json")
    prepared = managed(root, "data", ".restore-" + operation_id)
    data.parent.mkdir(parents=True, exist_ok=True)
    retained.parent.mkdir(parents=True, exist_ok=True)
    if journal.exists():
        state = json.loads(journal.read_text(encoding="utf-8"))
    else:
        state = {"had_data": data.exists(), "done": False}
        _journal(journal, state)
    if state["done"]:
        return str(retained) if retained.exists() else None
    # Presence of retained data records a completed rename even if the process
    # died before the next write. The original recovery point is never moved.
    displaced = retained.exists() or not state["had_data"]
    if displaced and not prepared.exists() and data.exists() and inventory(data) == info["files"]:
        state["done"] = True
        _journal(journal, state)
        return str(retained) if retained.exists() else None
    if prepared.exists() and inventory(prepared) != info["files"]:
        # An interrupted copy is disposable. Source was verified above and
        # neither current data nor retained data is touched by this retry.
        shutil.rmtree(prepared)
    if not prepared.exists():
        _copy(source, prepared)
    if inventory(prepared) != info["files"]:
        raise ValueError("prepared restore checksum mismatch")
    if not displaced:
        os.replace(data, retained)
    if info["exists"]:
        os.replace(prepared, data)
    else:
        shutil.rmtree(prepared)
    state["done"] = True
    _journal(journal, state)
    return str(retained) if retained.exists() else None


def _journal(path, state):
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
