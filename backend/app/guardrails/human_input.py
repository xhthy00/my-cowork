"""Eigent-style two-way human input gate for an active agent run."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable


class HumanInputHub:
    """Keep questions scoped to their task until the matching user reply arrives."""

    def __init__(self, emit: Callable[[dict[str, Any]], None], db_path: str | Path | None = None) -> None:
        self._emit = emit
        self._pending: dict[str, tuple[str, asyncio.Future[str], dict[str, Any]]] = {}
        self._clear_events: dict[str, asyncio.Event] = {}
        self._db_lock = threading.Lock()
        self._db: sqlite3.Connection | None = None
        if db_path is not None:
            path = Path(db_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(str(path), check_same_thread=False)
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS human_questions "
                "(question_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, event_json TEXT NOT NULL, "
                "status TEXT NOT NULL, answer TEXT, updated_at REAL NOT NULL)"
            )
            # A Future cannot survive a process exit. Preserve the question as
            # interrupted instead of claiming that a dead agent is still waiting.
            self._db.execute("UPDATE human_questions SET status='interrupted' WHERE status='pending'")
            self._db.commit()

    def _record(self, event: dict[str, Any], status: str, answer: str | None = None) -> None:
        if self._db is None:
            return
        with self._db_lock:
            self._db.execute(
                "INSERT INTO human_questions(question_id, task_id, event_json, status, answer, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(question_id) DO UPDATE SET "
                "status=excluded.status, answer=excluded.answer, updated_at=excluded.updated_at",
                (event["question_id"], event["task_id"], json.dumps(event, ensure_ascii=False),
                 status, answer, time.time()),
            )
            self._db.commit()

    def history(self, task_id: str) -> list[dict[str, Any]]:
        if self._db is None:
            return []
        with self._db_lock:
            rows = self._db.execute(
                "SELECT event_json, status, answer FROM human_questions WHERE task_id=? ORDER BY updated_at",
                (task_id,),
            ).fetchall()
        return [{**json.loads(event), "status": status, "answer": answer} for event, status, answer in rows]

    async def ask(
        self,
        task_id: str,
        agent: str,
        question: str,
        options: list[str] | None = None,
        fields: list[dict[str, Any]] | None = None,
    ) -> str:
        question = question.strip()
        if not task_id or not question:
            raise ValueError("An active task and a non-empty question are required")
        question_id = uuid.uuid4().hex
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        event = {
            "type": "human.ask",
            "task_id": task_id,
            "question_id": question_id,
            "agent": agent,
            "question": question,
            "options": [str(item).strip() for item in (options or []) if str(item).strip()][:4],
            "fields": [
                {
                    "label": str(field.get("label", "")).strip(),
                    "kind": field.get("kind") if field.get("kind") in ("single", "multiple", "text") else "text",
                    "options": [str(item).strip() for item in (field.get("options") or []) if str(item).strip()][:8],
                    "required": bool(field.get("required", False)),
                    "placeholder": str(field.get("placeholder", "")).strip(),
                }
                for field in (fields or [])[:10]
                if isinstance(field, dict) and str(field.get("label", "")).strip()
            ],
        }
        # Eigent registers its human-input listener before broadcasting the ask.
        self._pending[question_id] = (task_id, future, event)
        self._clear_events.setdefault(task_id, asyncio.Event()).clear()
        self._record(event, "pending")
        self._emit(event)
        try:
            return await future
        finally:
            self._pending.pop(question_id, None)
            if future.cancelled():
                self._record(event, "cancelled")
            if not self.pending(task_id):
                self._clear_events.pop(task_id).set()

    def reply(self, task_id: str, question_id: str, answer: str) -> bool:
        pending = self._pending.get(question_id)
        if pending is None or pending[0] != task_id or pending[1].done():
            return False
        value = answer.strip()
        if not value:
            return False
        pending[1].set_result(value)
        self._record(pending[2], "answered", value)
        self._emit({
            "type": "human.answered",
            "task_id": task_id,
            "question_id": question_id,
            "answer": value,
        })
        return True

    def pending(self, task_id: str) -> list[dict[str, Any]]:
        return [
            dict(event)
            for owner, future, event in self._pending.values()
            if owner == task_id and not future.done()
        ]

    async def wait_until_clear(self, task_id: str) -> None:
        """Pause other branches at their next safe boundary while a user decides."""
        while self.pending(task_id):
            await self._clear_events[task_id].wait()

    def cancel_task(self, task_id: str) -> None:
        for owner, future, _event in list(self._pending.values()):
            if owner == task_id and not future.done():
                future.cancel()
