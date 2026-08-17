"""L4 audit log for confirmations and forbidden commands."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class AuditStore:
    """SQLite audit trail for guardrail decisions."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                kind TEXT,
                tool TEXT,
                call_id TEXT,
                ok INTEGER,
                detail_json TEXT,
                at REAL
            )
            """
        )
        self._conn.commit()

    def log(
        self,
        *,
        kind: str,
        tool: str = "",
        call_id: str = "",
        ok: bool | None = None,
        task_id: str = "",
        detail: dict[str, Any] | None = None,
        at: float | None = None,
    ) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO audit_log(task_id, kind, tool, call_id, ok, detail_json, at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                task_id,
                kind,
                tool,
                call_id,
                None if ok is None else (1 if ok else 0),
                json.dumps(detail or {}, ensure_ascii=False, default=str),
                at if at is not None else time.time(),
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid or 0)

    def list_recent(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT id, task_id, kind, tool, call_id, ok, detail_json, at
            FROM audit_log
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            try:
                detail = json.loads(row[6] or "{}")
            except json.JSONDecodeError:
                detail = {}
            out.append(
                {
                    "id": row[0],
                    "task_id": row[1],
                    "kind": row[2],
                    "tool": row[3],
                    "call_id": row[4],
                    "ok": None if row[5] is None else bool(row[5]),
                    "detail": detail,
                    "at": row[7],
                }
            )
        return out

    def close(self) -> None:
        self._conn.close()
