"""Persisted task status store (SQLite)."""

from __future__ import annotations

import sqlite3
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
                source=excluded.source,
                text=excluded.text,
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
            "SELECT task_id, status, source, text, updated_at FROM tasks WHERE task_id = ?",
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
        }

    def close(self) -> None:
        self._conn.close()
