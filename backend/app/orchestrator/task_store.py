"""Persisted task status store (SQLite)."""

from __future__ import annotations

import sqlite3
import json
import uuid
import time
from pathlib import Path
from typing import Any


class TaskStore:
    """Persist task lifecycle status across process restarts."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                source TEXT,
                text TEXT,
                updated_at REAL
            )
            """
        )
        if 'origin' not in {row[1] for row in self._conn.execute('PRAGMA table_info(tasks)')}:
            self._conn.execute('ALTER TABLE tasks ADD COLUMN origin TEXT')
        self._conn.execute('CREATE TABLE IF NOT EXISTS task_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, event TEXT NOT NULL)')
        self._conn.execute('CREATE INDEX IF NOT EXISTS task_events_owner ON task_events(task_id, seq)')
        self._conn.execute('CREATE TABLE IF NOT EXISTS app_files (id TEXT PRIMARY KEY, app_id TEXT NOT NULL, path TEXT NOT NULL, task_id TEXT)')
        self._conn.commit()

    def upsert(
        self,
        task_id: str,
        status: str,
        *,
        source: str = "user",
        text: str = "",
    ) -> None:
        now = time.time()
        self._conn.execute(
            """
            INSERT INTO tasks(task_id, status, source, text, updated_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(task_id) DO UPDATE SET
                status=excluded.status,
                source=CASE WHEN tasks.origin IS NULL THEN excluded.source ELSE tasks.source END,
                text=CASE WHEN tasks.origin IS NULL THEN excluded.text ELSE tasks.text END,
                updated_at=excluded.updated_at
            """,
            (task_id, status, source, text, now),
        )
        self._conn.commit()

    def get_status(self, task_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT status FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        return str(row[0]) if row else None

    def get(self, task_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT task_id, status, source, text, updated_at, origin FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "task_id": row[0],
            "status": row[1],
            "source": row[2],
            "text": row[3],
            "updated_at": row[4],
            "origin": json.loads(row[5]) if row[5] else None,
        }

    def create_app_task(self, task_id: str, text: str, origin: dict[str, Any]) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                'INSERT OR IGNORE INTO tasks(task_id,status,source,text,updated_at,origin) VALUES(?,?,?,?,?,?)',
                (task_id, 'NEW', 'industry_app', text, time.time(), json.dumps(origin, ensure_ascii=False)),
            )
        return cursor.rowcount == 1

    def project_is_running(self, project_id: str) -> bool:
        return self._conn.execute("SELECT 1 FROM tasks WHERE json_extract(origin, '$.project_id')=? AND status IN ('NEW','RUNNING','CANCELLING') LIMIT 1", (project_id,)).fetchone() is not None

    def app_tasks(self, app_id: str | None = None) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT task_id FROM tasks WHERE origin IS NOT NULL AND (? IS NULL OR json_extract(origin, '$.app_id') = ?) ORDER BY updated_at DESC",
            (app_id, app_id),
        ).fetchall()
        return [self.get(row[0]) for row in rows]

    def append_event(self, task_id: str, event: dict[str, Any]) -> None:
        with self._conn:
            self._conn.execute('INSERT INTO task_events(task_id,event) VALUES(?,?)',
                               (task_id, json.dumps(event, ensure_ascii=False, default=str)))

    def events(self, task_id: str, after: int = 0) -> list[dict[str, Any]]:
        return [{'seq': row[0], 'event': json.loads(row[1])} for row in self._conn.execute(
            'SELECT seq,event FROM task_events WHERE task_id=? AND seq>? ORDER BY seq LIMIT 500', (task_id, after))]

    def interrupt_app_tasks(self) -> None:
        with self._conn:
            self._conn.execute("UPDATE tasks SET status='INTERRUPTED', updated_at=? WHERE origin IS NOT NULL AND status IN ('NEW','RUNNING','CANCELLING')", (time.time(),))

    def add_file(self, app_id: str, path: str, *, task_id: str | None = None) -> dict[str, str]:
        file_id = uuid.uuid4().hex
        with self._conn:
            self._conn.execute('INSERT INTO app_files VALUES(?,?,?,?)', (file_id, app_id, path, task_id))
        return {'id': file_id, 'name': Path(path).name}

    def get_file(self, app_id: str, file_id: str) -> dict[str, str] | None:
        row = self._conn.execute('SELECT id,path FROM app_files WHERE app_id=? AND id=?', (app_id, file_id)).fetchone()
        return {'id': row[0], 'path': row[1], 'name': Path(row[1]).name} if row else None

    def task_files(self, app_id: str, task_id: str) -> list[dict[str, str]]:
        return [{'id': row[0], 'name': Path(row[1]).name} for row in self._conn.execute(
            'SELECT id,path FROM app_files WHERE app_id=? AND task_id=?', (app_id, task_id))]

    def operations(self, task_id: str) -> list[dict[str, Any]]:
        latest = {}
        for row in self._conn.execute("SELECT event FROM task_events WHERE task_id=? AND json_extract(event, '$.type')='app.operation' ORDER BY seq", (task_id,)):
            event = json.loads(row[0])
            latest[event['operation_id']] = event
        return list(latest.values())

    def close(self) -> None:
        self._conn.close()
