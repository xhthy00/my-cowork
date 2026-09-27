"""Redacted, session-scoped tool and guardrail audit log."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_SECRET_KEY = re.compile(r"password|passwd|secret|token|api.?key|authorization|cookie|credential|private.?key", re.I)
_PRIVATE_INPUT = re.compile(r"^(args|preview|text|content|body|cmd|command|script|input|value|answer|result)$", re.I)
_INLINE_SECRET = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+|((?:api[_-]?key|token|password|secret)\s*[:=]\s*)[^\s,&]+")


def _redact(value: Any, key: str = "") -> Any:
    if _SECRET_KEY.search(key) or _PRIVATE_INPUT.match(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value[:20]]
    if isinstance(value, str):
        if key.lower() == "url":
            from urllib.parse import urlsplit, urlunsplit
            try:
                parts = urlsplit(value)
                value = urlunsplit((parts.scheme, parts.hostname or "", parts.path, "", ""))
            except ValueError:
                return "[REDACTED]"
        return _INLINE_SECRET.sub(lambda m: (m.group(1) or m.group(2)) + "[REDACTED]", value[:500])
    return value


class AuditStore:
    """SQLite audit trail for guardrail decisions."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
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
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_task ON audit_log(task_id, id)")
        self._conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_audit_tool_event "
            "ON audit_log(task_id, kind, call_id) "
            "WHERE kind IN ('tool_call', 'tool_result') AND call_id != ''"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS audit_tasks "
            "(task_id TEXT PRIMARY KEY, session_id TEXT NOT NULL)"
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_tasks(session_id)")
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
        if not task_id:
            from app.observability.trace import _runtime_task_id
            task_id = _runtime_task_id() or ""
        with self._lock:
            cur = self._conn.execute(
                """INSERT OR IGNORE INTO audit_log(task_id, kind, tool, call_id, ok, detail_json, at)
                   VALUES (?,?,?,?,?,?,?)""",
                (task_id, kind, tool, call_id,
                 None if ok is None else (1 if ok else 0),
                 json.dumps(_redact(detail or {}), ensure_ascii=False, default=str),
                 at if at is not None else time.time()),
            )
            self._conn.commit()
            return int(cur.lastrowid or 0)

    def list_recent(self, *, limit: int = 100, task_id: str = "", session_id: str = "") -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        query = "SELECT id, task_id, kind, tool, call_id, ok, detail_json, at FROM audit_log"
        if task_id:
            query += " WHERE task_id = ? ORDER BY id DESC LIMIT ?"
            args: tuple[Any, ...] = (task_id, limit)
        elif session_id:
            query += " WHERE task_id IN (SELECT task_id FROM audit_tasks WHERE session_id = ?) ORDER BY id DESC LIMIT ?"
            args = (session_id, limit)
        else:
            query += " ORDER BY id DESC LIMIT ?"
            args = (limit,)
        with self._lock:
            rows = self._conn.execute(query, args).fetchall()
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
                    "detail": _redact(detail),
                    "at": row[7],
                }
            )
        return out

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def on_trace(self, event: dict[str, Any]) -> None:
        etype = str(event.get("type") or "")
        if etype == "graph.start":
            task_id = str(event.get("task_id") or "")
            session_id = str(event.get("session_id") or "")
            if task_id and session_id:
                with self._lock:
                    self._conn.execute(
                        "INSERT INTO audit_tasks(task_id, session_id) VALUES (?, ?) "
                        "ON CONFLICT(task_id) DO UPDATE SET session_id=excluded.session_id",
                        (task_id, session_id),
                    )
                    self._conn.commit()
            return
        if etype not in {"tool.start", "tool.result"}:
            return
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        tool = str(event.get("tool") or payload.get("tool") or "")
        call_id = str(event.get("call_id") or payload.get("call_id") or "")
        if not tool:
            return
        result = str(event.get("result") or payload.get("result") or "")
        self.log(
            kind="tool_call" if etype == "tool.start" else "tool_result",
            task_id=str(event.get("task_id") or payload.get("task_id") or ""),
            tool=tool,
            call_id=call_id,
            ok=None if etype == "tool.start" else not result.lstrip().startswith(("[ERROR]", '{"error"')),
            detail={"agent": event.get("agent_id") or ""}
            if etype == "tool.start" else {"agent": event.get("agent_id") or "", "result_length": len(result)},
        )
