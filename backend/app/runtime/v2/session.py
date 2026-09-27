"""Session-scoped message thread (v2). session_id is the continuity key."""

from __future__ import annotations

import json
import hashlib
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

_LOCK = threading.Lock()
_MEMORY: dict[str, list[dict[str, Any]]] = {}
_COMPACTION: dict[str, dict[str, Any]] = {}


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
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS session_compaction ("
                "session_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )
            self._conn.commit()

    def load_compaction(self, session_id: str) -> dict[str, Any] | None:
        sid = (session_id or "").strip()
        if not sid:
            return None
        with _LOCK:
            if self._conn is None:
                return dict(_COMPACTION[sid]) if sid in _COMPACTION else None
            row = self._conn.execute(
                "SELECT payload FROM session_compaction WHERE session_id=?", (sid,)
            ).fetchone()
        if row is None:
            return None
        try:
            data = json.loads(row[0])
        except (ValueError, TypeError):
            return None
        return data if isinstance(data, dict) else None

    def save_compaction(self, session_id: str, state: dict[str, Any] | None) -> None:
        sid = (session_id or "").strip()
        if not sid:
            return
        with _LOCK:
            if self._conn is None:
                if state is None:
                    _COMPACTION.pop(sid, None)
                else:
                    _COMPACTION[sid] = dict(state)
                return
            if state is None:
                self._conn.execute("DELETE FROM session_compaction WHERE session_id=?", (sid,))
            else:
                self._conn.execute(
                    "INSERT INTO session_compaction(session_id,payload) VALUES (?,?) "
                    "ON CONFLICT(session_id) DO UPDATE SET payload=excluded.payload",
                    (sid, json.dumps(state, ensure_ascii=False)),
                )
            self._conn.commit()

    def write_compaction_transcript(
        self, session_id: str, messages: list[Any], boundary_index: int,
    ) -> str:
        """Export the exact older turns so the agent can re-read lost details."""
        if self.db_path is None or boundary_index <= 0:
            return ""
        name = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:24] + ".md"
        target = self.db_path.parent / "compaction-transcripts" / name
        lines = ["# 压缩前的会话原文", ""]
        for index, message in enumerate(messages[:boundary_index], 1):
            row = _serialize(message)
            role = str(row.get("type") or "unknown")
            content = str(row.get("content") or "")
            # Reasoning tags are private working text, not durable task evidence.
            content = re.sub(r"<think>[\s\S]*?</think>", "", content, flags=re.I)
            content = re.sub(r"<think>[\s\S]*$", "", content, flags=re.I)
            lines.extend((f"## {index}. {role}", "", content, ""))
            if row.get("tool_calls"):
                lines.extend(("工具调用：", "```json",
                              json.dumps(row["tool_calls"], ensure_ascii=False, indent=2),
                              "```", ""))
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(".tmp")
        temp.write_text("\n".join(lines), encoding="utf-8")
        temp.replace(target)
        return str(target)

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
            _COMPACTION.pop(sid, None)
            if self._conn is not None and sid:
                self._conn.execute(
                    "DELETE FROM session_thread WHERE session_id = ?", (sid,)
                )
                self._conn.execute(
                    "DELETE FROM session_compaction WHERE session_id = ?", (sid,)
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


def configure_session_store(db_path: str | Path) -> SessionStore:
    """Point the process-wide conversation journal at the backend data directory."""
    global _STORE
    path = Path(db_path)
    if _STORE is None or _STORE.db_path != path:
        _STORE = SessionStore(path)
    return _STORE


def load_thread(session_id: str) -> list[Any]:
    return get_session_store().load(session_id)


def save_thread(session_id: str, messages: list[Any]) -> None:
    get_session_store().save(session_id, messages)


def load_compaction(session_id: str) -> dict[str, Any] | None:
    return get_session_store().load_compaction(session_id)


def save_compaction(session_id: str, state: dict[str, Any] | None) -> None:
    get_session_store().save_compaction(session_id, state)


def write_compaction_transcript(
    session_id: str, messages: list[Any], boundary_index: int,
) -> str:
    return get_session_store().write_compaction_transcript(
        session_id, messages, boundary_index,
    )


def append_run(session_id: str, messages: list[Any]) -> list[Any]:
    return get_session_store().append(session_id, messages)
