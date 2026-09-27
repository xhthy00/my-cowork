"""Durable desktop conversation snapshot, independent of renderer localStorage."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class DesktopSessionStore:
    def __init__(self, db_path: str | Path) -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS desktop_sessions "
            "(id INTEGER PRIMARY KEY CHECK(id = 1), payload TEXT NOT NULL, updated_at REAL NOT NULL)"
        )
        self._conn.commit()

    def load(self) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT payload FROM desktop_sessions WHERE id = 1").fetchone()
        return json.loads(row[0]) if row else None

    def save(self, snapshot: dict[str, Any]) -> None:
        payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self._conn.execute(
                "INSERT INTO desktop_sessions(id, payload, updated_at) VALUES (1, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at",
                (payload, time.time()),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
