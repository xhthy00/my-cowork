"""Persisted lifecycle decisions. The desktop owns process start/stop, not data."""
from __future__ import annotations

import copy
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from . import registry
from .locks import FileLock
from .package import AppManifest, app_root, stage_zip
from .snapshots import create_snapshot, inventory, managed, restore_snapshot
from .development import package_path, stage_development

TERMINAL = {"committed", "restored", "cancelled"}


def operation(root):
    return registry.read(root, "operation")


def public_operation(op):
    if not op:
        return None
    return {k: v for k, v in op.items() if k in {
        "id", "app_id", "action", "phase", "error", "retained", "snapshot", "created_at"
    }}


def launch_args(*args):
    return [sys.executable, *args] if getattr(sys, "frozen", False) else [sys.executable, "-m", "app.main", *args]


class Maintenance:
    def __init__(self, root: Path):
        self.root = app_root(root)
        self.lock = FileLock(self.root, "operation").acquire()
        self.run_lock = FileLock(self.root, "running")

    def close(self):
        self.run_lock.close()
        self.lock.close()

    def save(self, op, phase=None):
        if phase:
            op["phase"] = phase
        registry.write(self.root, "operation", op)
        return op

    def begin(self, action, app_id=None, raw=None, sha256=None):
        previous = operation(self.root)
        if previous and previous["phase"] not in TERMINAL:
            raise ValueError("上次操作尚未完成，请先恢复")
        if action not in {"install", "develop", "enable", "disable", "remove", "rollback", "restart"}:
            raise ValueError("unsupported lifecycle action")
        if action == "install":
            result = stage_zip(raw, sha256, self.root)
            app_id = result["id"]
        elif action == "develop":
            result = stage_development(raw, sha256, self.root)
            app_id = result['id']
            if result['unchanged']:
                return {'app_id': app_id, 'unchanged': True}
        state = registry.read(self.root)
        source = copy.deepcopy(state["apps"].get(app_id))
        if action != "restart" and source is None:
            raise ValueError("application not found")
        target = copy.deepcopy(source)
        if source and source.get("version"):
            source.pop("candidate", None)
        if source and source.get("recovery_operation") and action != "disable":
            raise ValueError("请先重试恢复未完成的数据操作")
        if action in {"install", "develop", "enable"}:
            if target.get("candidate"):
                target.update(target.pop("candidate"))
            if not target.get("version"):
                raise ValueError("没有可启用的包")
            manifest = AppManifest.model_validate(target["manifest"])
            target.update(enabled=True, removed=False, data_version=manifest.data.version or "legacy")
        elif action in {"disable", "remove"}:
            target.update(enabled=False, removed=action == "remove", status="disabled")
        elif action == "rollback":
            point = source.get("recovery")
            if not point:
                raise ValueError("没有可用的数据恢复点")
            target = copy.deepcopy(point["entry"])
        if target:
            target.pop("error", None)
        from datetime import datetime, timezone
        op = {"id": uuid.uuid4().hex, "token": secrets.token_hex(32), "action": action,
              "app_id": app_id, "source": source, "target": target, "phase": "staged",
              "created_at": datetime.now(timezone.utc).isoformat()}
        return self.save(op)

    def prepare(self):
        op = operation(self.root)
        if op["phase"] not in {"staged", "draining"}:
            raise ValueError("operation is not ready to prepare")
        self.run_lock.acquire()  # Actual OS exclusion, not a process-status guess.
        if op["action"] in {"install", "develop", "enable", "rollback"}:
            op["snapshot"] = create_snapshot(self.root, op["app_id"], op["id"])
        self.save(op, "snapshot_ready")
        if op["action"] == "rollback":
            self.save(op, "migrating")
            op["retained"] = restore_snapshot(self.root, op["app_id"], op["id"], op["source"]["recovery"]["snapshot"])
            self.save(op)
        elif op["action"] in {"install", "develop", "enable"}:
            source_version = op["source"].get("data_version", "legacy")
            target_version = op["target"]["data_version"]
            if source_version != target_version and op["snapshot"]["exists"]:
                self.save(op, "migrating")
                self._migrate(op)
        return self.starting(op)

    def _migrate(self, op):
        self.run_lock.close()
        env = {**os.environ, "MY_COWORK_INDUSTRY_APPS_ROOT": str(self.root),
               "MY_COWORK_OPERATION_TOKEN": op["token"], "MY_COWORK_PARENT_PIPE": "1"}
        # Keep stdin open: EOF terminates the worker if its supervisor disappears.
        with tempfile.TemporaryFile() as log:
            proc = subprocess.Popen(launch_args("--industry-migrate"), env=env, stdin=subprocess.PIPE,
                                    stdout=log, stderr=log, creationflags=0x08000000 if os.name == "nt" else 0)
            try:
                proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                raise ValueError("数据迁移超时")
            finally:
                proc.stdin.close()
                self.run_lock.acquire()
            if proc.returncode:
                log.seek(0, 2)
                log.seek(max(0, log.tell() - 3000))
                raise ValueError("数据迁移失败：" + log.read().decode("utf-8", errors="replace"))

    def starting(self, op):
        self.save(op, "starting" if not op.get("restoring") else "restoring")
        self.run_lock.close()
        return {"token": op["token"], "id": op["id"]}

    def cancel(self, *, keep_candidate=False):
        op = operation(self.root)
        if op["phase"] not in {"staged", "draining"}:
            raise ValueError("正在保存或切换，不能立即取消")
        state = registry.read(self.root)
        if op.get("app_id") and op.get("source"):
            source = copy.deepcopy(op["source"])
            if keep_candidate and op["action"] in {"install", "develop", "enable"}:
                candidate = state["apps"][op["app_id"]].get("candidate")
                if candidate:
                    source["candidate"] = candidate
            state["apps"][op["app_id"]] = source
        op["phase"] = "cancelled"
        registry.commit_operation(self.root, state, op)
        return op

    def disable_failed(self, failures):
        """Ordinary startup may disable broken apps, but never restore their data."""
        op = operation(self.root)
        if op["action"] != "restart" or op["phase"] != "starting" or op.get("restoring"):
            raise ValueError("only ordinary startup can disable failed apps")
        self.run_lock.acquire()
        state = registry.read(self.root)
        for failed in failures:
            entry = state["apps"][failed["id"]]
            entry.update(enabled=False, status="load_failed", error=failed.get("error", "启动失败"))
        registry.commit_operation(self.root, state, op)
        return self.starting(op)

    def quarantine(self):
        """Keep all evidence and data; allow other apps to start without this one."""
        self.run_lock.acquire()
        op = operation(self.root)
        if not op or not op.get("app_id") or op["phase"] in TERMINAL:
            raise ValueError("没有需要隔离的失败操作")
        state = registry.read(self.root)
        entry = state["apps"][op["app_id"]]
        entry.update(enabled=False, status="recovery_required", recovery_operation=copy.deepcopy(op), error=op.get("error", "恢复未完成"))
        op["phase"] = "cancelled"
        registry.commit_operation(self.root, state, op)
        self.run_lock.close()
        return public_operation(op)

    def retry(self, app_id):
        state = registry.read(self.root)
        entry = state["apps"].get(app_id, {})
        op = entry.get("recovery_operation")
        if op:
            current = operation(self.root)
            if current and current["phase"] not in TERMINAL:
                raise ValueError("已有操作需要恢复")
            op["token"] = secrets.token_hex(32)
            self.save(op, "recovery_required")
        return public_operation(operation(self.root))

    def restore(self, error=""):
        op = operation(self.root)
        if op is None or op["phase"] in TERMINAL:
            return None
        self.run_lock.acquire()
        if op["phase"] in {"staged", "draining", "snapshot_ready"} and op["action"] != "rollback":
            # No candidate code has executed. Still validate the old runtime
            # under the operation lock before declaring it available again.
            op.update(restoring=True, target=copy.deepcopy(op["source"]), error=error or "上次操作中断，未改动业务数据")
            return self.starting(op)
        op.update(restoring=True, error=error or op.get("error", "上次更新中断"))
        self.save(op, "restoring")
        try:
            if op.get("snapshot"):
                # Manual rollback uses its own pre-rollback snapshot on failure.
                restore_id = op.setdefault("restore_id", uuid.uuid4().hex)
                journal = managed(self.root, "retained", restore_id + ".json")
                if journal.exists() and json.loads(journal.read_text(encoding="utf-8"))["done"]:
                    if inventory(managed(self.root, "data", op["app_id"])) != op["snapshot"]["files"]:
                        restore_id = op["restore_id"] = uuid.uuid4().hex
                self.save(op)
                op["retained"] = restore_snapshot(self.root, op["app_id"], restore_id, op["snapshot"])
            op["target"] = copy.deepcopy(op["source"])
            return self.starting(op)
        except Exception as exc:
            op["error"] = str(exc)
            self.save(op, "recovery_required")
            raise

    def commit(self):
        op = operation(self.root)
        if op["phase"] not in {"starting", "restoring"}:
            raise ValueError("operation has not started a candidate")
        state = registry.read(self.root)
        entry = op["target"]
        if entry:
            if not op.get("restoring") and op["action"] in {"install", "develop", "enable"} and (op["source"].get("version"), op["source"].get('dev_revision')) != (entry.get("version"), entry.get('dev_revision')) and op["source"].get("version") and op.get("snapshot"):
                previous = {k: v for k, v in op["source"].items() if k not in {"recovery", "candidate"}}
                entry["recovery"] = {"entry": previous, "snapshot": op["snapshot"]}
            entry["status"] = "ready" if entry.get("enabled") else "disabled"
            state["apps"][op["app_id"]] = entry
        op["phase"] = "restored" if op.get("restoring") else "committed"
        registry.commit_operation(self.root, state, op)
        if op["phase"] == "committed" and op["action"] in {"install", "develop", "enable"} and entry:
            old_point = (op.get("source") or {}).get("recovery", {}).get("snapshot")
            new_point = entry.get("recovery", {}).get("snapshot")
            if old_point and new_point and old_point["id"] != new_point["id"]:
                # Only superseded ordinary recovery points are eligible. Failed
                # operations and explicit rollback copies are never collected.
                try:
                    path = managed(self.root, "recovery", old_point["id"])
                    if path.is_dir():
                        shutil.rmtree(path)
                except OSError as exc:
                    op["cleanup_warning"] = str(exc)
                    self.save(op)
        return public_operation(op)


def runtime_entries(root, token=""):
    state = registry.read(root)
    op = operation(root)
    if op and op["phase"] not in TERMINAL:
        if not token or not secrets.compare_digest(op["token"], token) or op["phase"] not in {"starting", "restoring"}:
            raise RuntimeError("行业应用存在未完成操作，需先恢复")
        if op["target"]:
            state["apps"][op["app_id"]] = op["target"]
    return [{"id": k, **v} for k, v in state["apps"].items()]


def migrate_worker():
    import importlib
    from .sdk import MigrationContext
    root = app_root()
    op = operation(root)
    if not op or op["phase"] != "migrating" or not secrets.compare_digest(op["token"], os.environ.get("MY_COWORK_OPERATION_TOKEN", "")):
        raise RuntimeError("invalid migration operation")
    with FileLock(root, "running"):
        target = op["target"]
        package = package_path(root, op["app_id"], target) / 'backend'
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(package))
        module, name = target["manifest"]["data"]["migration_entry"].split(":")
        callback = getattr(importlib.import_module(module), name)
        result = callback(MigrationContext(op["app_id"], managed(root, "data", op["app_id"]),
                                          op["source"].get("version"), target["version"],
                                          op["source"].get("data_version", "legacy"), target["data_version"]))
        import inspect
        if inspect.isawaitable(result):
            import asyncio
            asyncio.run(result)
