"""Session-scoped message thread (v2). session_id is the continuity key."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

_LOCK = threading.Lock()
_MEMORY: dict[str, list[dict[str, Any]]] = {}


def _default_db() -> Path | None:
    import os

    raw = os.environ.get("MY_COWORK_DATA_DIR")
    if not raw:
        return Path.home() / ".my-cowork" / "sessions.db"
    return Path(raw) / "sessions.db"


def _serialize(message: Any) -> dict[str, Any]:
    if isinstance(message, dict):
        return dict(message)
    tool_calls = getattr(message, "tool_calls", None) or []
    serial_calls: list[dict[str, Any]] = []
    for call in tool_calls:
        if isinstance(call, dict):
            serial_calls.append(dict(call))
        else:
            serial_calls.append(
                {
                    "id": str(getattr(call, "id", "") or ""),
                    "name": str(getattr(call, "name", "") or ""),
                    "args": getattr(call, "args", {}) or {},
                }
            )
    mtype = str(getattr(message, "type", None) or message.__class__.__name__)
    return {
        "type": mtype,
        "content": getattr(message, "content", "") or "",
        "name": getattr(message, "name", None),
        "tool_call_id": getattr(message, "tool_call_id", None),
        "tool_calls": serial_calls,
    }


def _deserialize(row: dict[str, Any]) -> Any:
    mtype = str(row.get("type") or "")
    content = row.get("content") or ""
    if mtype in {"human", "HumanMessage", "user"}:
        return HumanMessage(content=content)
    if mtype in {"system", "SystemMessage"}:
        return SystemMessage(content=content)
    if mtype in {"tool", "ToolMessage"}:
        return ToolMessage(
            content=str(content),
            tool_call_id=str(row.get("tool_call_id") or ""),
            name=str(row.get("name") or ""),
        )
    return AIMessage(
        content=content,
        tool_calls=list(row.get("tool_calls") or []),
        name=row.get("name"),
    )


class SessionStore:
    """SQLite-backed session threads; falls back to process memory."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else _default_db()
        self._conn: sqlite3.Connection | None = None
        if self.db_path is not None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_thread (
                    session_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at REAL
                )
                """
            )
            self._conn.commit()

    def load(self, session_id: str) -> list[Any]:
        sid = (session_id or "").strip()
        if not sid:
            return []
        with _LOCK:
            if self._conn is None:
                return [_deserialize(m) for m in _MEMORY.get(sid, [])]
            row = self._conn.execute(
                "SELECT payload FROM session_thread WHERE session_id = ?",
                (sid,),
            ).fetchone()
        if not row:
            return []
        try:
            data = json.loads(row[0])
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [_deserialize(m) for m in data if isinstance(m, dict)]

    def save(self, session_id: str, messages: list[Any]) -> None:
        sid = (session_id or "").strip()
        if not sid:
            return
        payload = [_serialize(m) for m in messages]
        blob = json.dumps(payload, ensure_ascii=False, default=str)
        import time

        with _LOCK:
            if self._conn is None:
                _MEMORY[sid] = payload
                return
            self._conn.execute(
                """
                INSERT INTO session_thread(session_id, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (sid, blob, time.time()),
            )
            self._conn.commit()

    def append(self, session_id: str, extra: list[Any]) -> list[Any]:
        current = self.load(session_id)
        merged = [*current, *extra]
        self.save(session_id, merged)
        return merged

    def clear(self, session_id: str) -> None:
        sid = (session_id or "").strip()
        with _LOCK:
            _MEMORY.pop(sid, None)
            if self._conn is not None and sid:
                self._conn.execute(
                    "DELETE FROM session_thread WHERE session_id = ?", (sid,)
                )
                self._conn.commit()


_STORE: SessionStore | None = None


def get_session_store(db_path: str | Path | None = None) -> SessionStore:
    global _STORE
    if db_path is not None:
        return SessionStore(db_path)
    if _STORE is None:
        _STORE = SessionStore()
    return _STORE


def load_thread(session_id: str) -> list[Any]:
    return get_session_store().load(session_id)


def save_thread(session_id: str, messages: list[Any]) -> None:
    get_session_store().save(session_id, messages)


def append_run(session_id: str, messages: list[Any]) -> list[Any]:
    return get_session_store().append(session_id, messages)
