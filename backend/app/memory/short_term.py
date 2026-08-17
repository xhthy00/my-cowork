"""Short-term context store per task (memory or SQLite)."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class ShortTermStore:
    """Store task-scoped messages.

    - No ``db_path`` → in-memory dict (tests / ephemeral).
    - With ``db_path`` → SQLite table ``short_term`` (survives restarts).
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._ctx: dict[str, list[Any]] = {}
        self._conn: sqlite3.Connection | None = None
        if db_path is not None:
            path = Path(db_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(path))
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS short_term (
                    task_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    role TEXT,
                    content TEXT,
                    payload_json TEXT,
                    at REAL,
                    PRIMARY KEY (task_id, seq)
                )
                """
            )
            self._conn.commit()

    def get(self, task_id: str) -> list[Any]:
        if self._conn is None:
            return list(self._ctx.get(task_id, []))
        rows = self._conn.execute(
            """
            SELECT role, content, payload_json FROM short_term
            WHERE task_id = ? ORDER BY seq ASC
            """,
            (task_id,),
        ).fetchall()
        out: list[Any] = []
        for role, content, payload_json in rows:
            if payload_json:
                try:
                    out.append(json.loads(payload_json))
                    continue
                except json.JSONDecodeError:
                    pass
            out.append({"role": role or "user", "content": content or ""})
        return out

    def append(self, task_id: str, msg: Any) -> None:
        if self._conn is None:
            self._ctx.setdefault(task_id, []).append(msg)
            return
        row = self._conn.execute(
            "SELECT COALESCE(MAX(seq), -1) FROM short_term WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        seq = int(row[0]) + 1 if row else 0
        if isinstance(msg, dict):
            role = str(msg.get("role") or "")
            content = str(msg.get("content") or "")
            payload = json.dumps(msg, ensure_ascii=False, default=str)
        else:
            role = ""
            content = str(msg)
            payload = json.dumps(msg, ensure_ascii=False, default=str)
        self._conn.execute(
            """
            INSERT INTO short_term(task_id, seq, role, content, payload_json, at)
            VALUES (?,?,?,?,?,?)
            """,
            (task_id, seq, role, content, payload, time.time()),
        )
        self._conn.commit()

    def clear(self, task_id: str) -> None:
        if self._conn is None:
            self._ctx.pop(task_id, None)
            return
        self._conn.execute("DELETE FROM short_term WHERE task_id = ?", (task_id,))
        self._conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
