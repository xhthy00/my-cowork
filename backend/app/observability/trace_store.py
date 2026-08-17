"""SQLite persistence for TraceBus events."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class TraceStore:
    """Append-only SQLite log of trace events, keyed by task_id."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trace_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                type TEXT,
                payload_json TEXT,
                created_at REAL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_trace_task ON trace_events(task_id)"
        )
        self._conn.commit()

    def append(self, event: dict[str, Any]) -> int:
        """Persist one event; returns row id. Safe to use as TraceBus subscriber."""
        task_id = str(event.get("task_id") or "")
        etype = str(event.get("type") or "")
        created = time.time()
        cur = self._conn.execute(
            "INSERT INTO trace_events(task_id, type, payload_json, created_at) VALUES (?,?,?,?)",
            (task_id, etype, json.dumps(event, ensure_ascii=False, default=str), created),
        )
        self._conn.commit()
        return int(cur.lastrowid or 0)

    def list_for_task(self, task_id: str, *, limit: int = 500) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT id, task_id, type, payload_json, created_at
            FROM trace_events
            WHERE task_id = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (task_id, limit),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row_id, tid, etype, payload_json, created_at in rows:
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                payload = {"raw": payload_json}
            out.append(
                {
                    "id": row_id,
                    "task_id": tid,
                    "type": etype,
                    "event": payload,
                    "created_at": created_at,
                }
            )
        return out

    def close(self) -> None:
        self._conn.close()
