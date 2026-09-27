"""SQLite source of truth for automations, claims, runs, and run events."""

from __future__ import annotations

import json
import hashlib
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .models import Automation, AutomationRun, next_fire_time
from app.guardrails.approval import valid_automation_commands


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


class AutomationStore:
    def __init__(self, db_path: str | Path) -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._workspace_root = path.parent / "automation-workspaces"
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS automations (
                id TEXT PRIMARY KEY, enabled INTEGER NOT NULL, next_run REAL,
                data TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_automations_due ON automations(enabled, next_run);
            CREATE TABLE IF NOT EXISTS automation_runs (
                run_id TEXT PRIMARY KEY, task_id TEXT NOT NULL,
                started_at REAL NOT NULL, status TEXT NOT NULL, data TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_automation_runs_task ON automation_runs(task_id, started_at DESC);
            CREATE TABLE IF NOT EXISTS automation_run_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                event TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_automation_events_run ON automation_run_events(run_id, id);
            CREATE TABLE IF NOT EXISTS automation_tool_attempts (
                run_id TEXT NOT NULL, call_id TEXT NOT NULL, tool TEXT NOT NULL,
                checkpoint_key TEXT NOT NULL, status TEXT NOT NULL,
                PRIMARY KEY (run_id, call_id)
            );
            CREATE TABLE IF NOT EXISTS automation_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def meta(self, key: str) -> str | None:
        with self._lock:
            row = self._db.execute("SELECT value FROM automation_meta WHERE key=?", (key,)).fetchone()
            return str(row[0]) if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO automation_meta VALUES (?, ?)", (key, value))
            self._db.commit()

    def save(self, task: Automation, *, preserve_next_run: bool = False) -> Automation:
        task.schedule.validate()
        task.always_allowed_commands = valid_automation_commands(task.always_allowed_commands)
        if not task.title.strip() or not task.instructions.strip():
            raise ValueError("Title and instructions are required")
        if task.notify_target is not None:
            task.notify_target = task.notify_target.strip() or None
            if task.notify_target and (not task.notify_target.startswith("lark:")
                                       or not task.notify_target.removeprefix("lark:").strip()):
                raise ValueError("Notification target must be lark:<chat_id>")
        if not task.workspace:
            suffix = hashlib.sha256(task.id.encode("utf-8")).hexdigest()[:16]
            task.workspace = str(self._workspace_root / suffix)
        task.updated_at = time.time()
        if not preserve_next_run:
            task.next_run = (
                next_fire_time(task.schedule, run_count=task.run_count)
                if task.enabled and (task.max_runs is None or task.run_count < task.max_runs)
                else None
            )
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO automations(id, enabled, next_run, data) VALUES (?, ?, ?, ?)",
                (task.id, int(task.enabled), task.next_run, _json(task.to_dict())),
            )
            self._db.commit()
        return task

    def get(self, task_id: str) -> Automation | None:
        with self._lock:
            row = self._db.execute("SELECT data FROM automations WHERE id=?", (task_id,)).fetchone()
            return Automation.from_dict(json.loads(row[0])) if row else None

    def list(self) -> list[Automation]:
        with self._lock:
            rows = self._db.execute(
                "SELECT data FROM automations ORDER BY next_run IS NULL, next_run, id"
            ).fetchall()
            return [Automation.from_dict(json.loads(row[0])) for row in rows]

    def delete(self, task_id: str) -> bool:
        with self._lock:
            row = self._db.execute("DELETE FROM automations WHERE id=?", (task_id,))
            if not row.rowcount:
                return False
            self._db.execute(
                "DELETE FROM automation_run_events WHERE run_id IN "
                "(SELECT run_id FROM automation_runs WHERE task_id=?)", (task_id,)
            )
            self._db.execute("DELETE FROM automation_runs WHERE task_id=?", (task_id,))
            self._db.execute(
                "DELETE FROM automation_tool_attempts WHERE run_id NOT IN "
                "(SELECT run_id FROM automation_runs)"
            )
            self._db.commit()
            return True

    def due_ids(self, *, now: float | None = None) -> list[str]:
        now = time.time() if now is None else now
        with self._lock:
            return [str(row[0]) for row in self._db.execute(
                "SELECT id FROM automations WHERE enabled=1 AND next_run IS NOT NULL "
                "AND next_run<=? ORDER BY next_run", (now,)
            ).fetchall()]

    def _save_run(self, run: AutomationRun) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO automation_runs(run_id, task_id, started_at, status, data) "
            "VALUES (?, ?, ?, ?, ?)",
            (run.run_id, run.task_id, run.started_at, run.status, _json(run.to_dict())),
        )

    def claim(self, task_id: str, *, trigger: str, now: float | None = None) -> AutomationRun | None:
        """Atomically reserve one due/manual run and advance its next fire time."""
        now = time.time() if now is None else now
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row = self._db.execute("SELECT data FROM automations WHERE id=?", (task_id,)).fetchone()
                if row is None:
                    self._db.rollback()
                    return None
                task = Automation.from_dict(json.loads(row[0]))
                if trigger != "manual" and (not task.enabled or task.next_run is None or task.next_run > now):
                    self._db.rollback()
                    return None
                active = self._db.execute(
                    "SELECT 1 FROM automation_runs WHERE task_id=? AND status IN ('running','waiting_user','recovery_review') LIMIT 1",
                    (task_id,),
                ).fetchone()
                if active:
                    if trigger != "manual":
                        skipped = AutomationRun(task_id=task_id, trigger=trigger,
                                                scheduled_for=task.next_run, status="skipped",
                                                finished_at=now, error="Previous run is still active")
                        self._save_run(skipped)
                        task.next_run = next_fire_time(task.schedule, after=now, run_count=task.run_count + 1)
                        self._db.execute("UPDATE automations SET next_run=?, data=? WHERE id=?",
                                         (task.next_run, _json(task.to_dict()), task.id))
                        self._db.commit()
                    else:
                        self._db.rollback()
                    return None
                run = AutomationRun(task_id=task_id, trigger=trigger,
                                    scheduled_for=task.next_run if trigger != "manual" else None)
                self._save_run(run)
                if trigger != "manual":
                    task.next_run = (
                        next_fire_time(task.schedule, after=now, run_count=task.run_count + 1)
                        if task.max_runs is None or task.run_count + 1 < task.max_runs else None
                    )
                    self._db.execute("UPDATE automations SET next_run=?, data=? WHERE id=?",
                                     (task.next_run, _json(task.to_dict()), task.id))
                self._db.commit()
                return run
            except Exception:
                self._db.rollback()
                raise

    def update_run(self, run: AutomationRun) -> None:
        with self._lock:
            self._save_run(run)
            self._db.commit()

    def finish(self, run: AutomationRun) -> None:
        run.finished_at = run.finished_at or time.time()
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                previous = self._db.execute(
                    "SELECT data FROM automation_runs WHERE run_id=?", (run.run_id,)
                ).fetchone()
                if previous and AutomationRun.from_dict(json.loads(previous[0])).finished_at is not None:
                    self._db.rollback()
                    return
                self._save_run(run)
                row = self._db.execute("SELECT data FROM automations WHERE id=?", (run.task_id,)).fetchone()
                if row:
                    task = Automation.from_dict(json.loads(row[0]))
                    task.last_run = run.finished_at
                    task.last_status = run.status
                    task.run_count += 1
                    task.updated_at = time.time()
                    self._db.execute("UPDATE automations SET next_run=?, data=? WHERE id=?",
                                     (task.next_run, _json(task.to_dict()), task.id))
                self._db.commit()
            except Exception:
                self._db.rollback()
                raise

    def get_run(self, run_id: str) -> AutomationRun | None:
        with self._lock:
            row = self._db.execute("SELECT data FROM automation_runs WHERE run_id=?", (run_id,)).fetchone()
            return AutomationRun.from_dict(json.loads(row[0])) if row else None

    def runs(self, task_id: str, *, limit: int = 50) -> list[AutomationRun]:
        with self._lock:
            rows = self._db.execute(
                "SELECT data FROM automation_runs WHERE task_id=? ORDER BY started_at DESC LIMIT ?",
                (task_id, max(1, min(limit, 200))),
            ).fetchall()
            return [AutomationRun.from_dict(json.loads(row[0])) for row in rows]

    def append_event(self, run_id: str, event: dict) -> None:
        with self._lock:
            self._db.execute("INSERT INTO automation_run_events(run_id, event) VALUES (?, ?)",
                             (run_id, _json(event)))
            self._db.commit()

    def tool_started(self, run_id: str, call_id: str, tool: str, checkpoint_key: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO automation_tool_attempts VALUES (?, ?, ?, ?, 'started')",
                (run_id, call_id, tool, checkpoint_key),
            )
            self._db.commit()

    def tool_completed(self, run_id: str, call_id: str) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE automation_tool_attempts SET status='completed' WHERE run_id=? AND call_id=?",
                (run_id, call_id),
            )
            self._db.commit()

    def unfinished_tools(self, run_id: str) -> list[dict[str, str]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT call_id, tool, checkpoint_key FROM automation_tool_attempts "
                "WHERE run_id=? AND status='started'", (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def events(self, run_id: str, *, limit: int = 1000) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT event FROM automation_run_events WHERE run_id=? ORDER BY id DESC LIMIT ?",
                (run_id, max(1, min(limit, 5000))),
            ).fetchall()
            return [json.loads(row[0]) for row in reversed(rows)]

    def mark_seen(self, task_id: str) -> bool:
        task = self.get(task_id)
        if task is None:
            return False
        task.seen_runs_at = time.time()
        return bool(self.save(task, preserve_next_run=True))

    def recover_interrupted(self) -> list[AutomationRun]:
        """Reclaim unfinished runs for the scheduler on backend startup."""
        recovered: list[AutomationRun] = []
        with self._lock:
            rows = self._db.execute(
                "SELECT data FROM automation_runs WHERE status IN ('running','waiting_user')"
            ).fetchall()
            for row in rows:
                run = AutomationRun.from_dict(json.loads(row[0]))
                task_row = self._db.execute("SELECT data FROM automations WHERE id=?", (run.task_id,)).fetchone()
                if not task_row:
                    run.status = "error"
                    run.error = "Automation was deleted before recovery"
                    run.finished_at = time.time()
                else:
                    last_end = self._db.execute(
                        "SELECT event FROM automation_run_events WHERE run_id=? ORDER BY id DESC",
                        (run.run_id,),
                    ).fetchall()
                    end = None
                    for item in last_end:
                        event = json.loads(item[0])
                        if event.get("type") == "graph.end":
                            end = event
                            break
                    if end:
                        state = str(end.get("status") or "")
                        run.status = "error" if state == "error" else "cancelled" if state == "cancelled" else "ok"
                        run.result_text = str(end.get("summary") or "")
                        run.error = str(end.get("error") or "") or None
                        run.finished_at = time.time()
                    else:
                        from app.runtime.v2.session import load_thread
                        from langchain_core.messages import ToolMessage

                        uncertain: list[dict[str, str]] = []
                        for attempt in self.unfinished_tools(run.run_id):
                            saved = load_thread(attempt["checkpoint_key"])
                            if any(isinstance(msg, ToolMessage)
                                   and msg.tool_call_id == attempt["call_id"] for msg in saved):
                                self.tool_completed(run.run_id, attempt["call_id"])
                            elif attempt["tool"] != "ask_human":
                                uncertain.append({"tool": attempt["tool"], "call_id": attempt["call_id"]})
                        run.recovery_tools = uncertain
                        if uncertain:
                            run.status = "recovery_review"
                        else:
                            run.status = "running"
                            run.resume_count += 1
                            recovered.append(run)
                self._save_run(run)
                if run.finished_at is not None and task_row:
                    task = Automation.from_dict(json.loads(task_row[0]))
                    task.last_run = run.finished_at
                    task.last_status = run.status
                    task.run_count += 1
                    self._db.execute("UPDATE automations SET data=? WHERE id=?",
                                     (_json(task.to_dict()), task.id))
            self._db.commit()
        return recovered
