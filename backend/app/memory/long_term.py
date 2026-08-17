"""L6 long-term vector memory backed by SQLite + sqlite-vec."""

from __future__ import annotations

import re
import sqlite3
import struct
import time
from pathlib import Path
from typing import Any, Callable

import sqlite_vec

EmbedFn = Callable[[str], list[float]]

_DEFAULT_DIM = 64


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


class LongTermStore:
    """Persist memories and retrieve top-k by embedding similarity."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        embed_fn: EmbedFn | None = None,
        dim: int = _DEFAULT_DIM,
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._embed = embed_fn
        self.dim = dim
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.enable_load_extension(True)
        self._conn.load_extension(sqlite_vec.loadable_path())
        self._conn.enable_load_extension(False)
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                kind TEXT,
                content TEXT NOT NULL,
                embedding BLOB,
                created_at REAL,
                expires_at REAL
            )
            """
        )
        # vec0 virtual table — rowid aligns with memory.id
        try:
            self._conn.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_memory USING vec0(embedding float[{self.dim}])"
            )
        except sqlite3.OperationalError:
            # Already exists with same schema
            pass
        self._conn.commit()

    def _vector(self, text: str) -> list[float]:
        if self._embed is not None:
            vec = self._embed(text)
        else:
            from app.llm.gateway import embed

            vec = embed(text, dim=self.dim)
        if len(vec) != self.dim:
            # Pad / truncate to configured dim
            if len(vec) < self.dim:
                vec = list(vec) + [0.0] * (self.dim - len(vec))
            else:
                vec = list(vec[: self.dim])
        return vec

    def write(
        self,
        content: str,
        kind: str = "note",
        *,
        task_id: str | None = None,
        expires_at: float | None = None,
    ) -> int:
        vec = self._vector(content)
        blob = _pack(vec)
        now = time.time()
        cur = self._conn.execute(
            "INSERT INTO memory(task_id, kind, content, embedding, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, kind, content, blob, now, expires_at),
        )
        rowid = int(cur.lastrowid)
        self._conn.execute(
            "INSERT INTO vec_memory(rowid, embedding) VALUES (?, ?)",
            (rowid, blob),
        )
        self._conn.commit()
        return rowid

    def query(self, text: str, k: int = 3) -> list[dict[str, Any]]:
        vec = self._vector(text)
        blob = _pack(vec)
        rows = self._conn.execute(
            """
            SELECT m.id, m.kind, m.content, m.task_id, m.created_at,
                   v.distance
            FROM vec_memory AS v
            JOIN memory AS m ON m.id = v.rowid
            WHERE v.embedding MATCH ?
              AND k = ?
            ORDER BY v.distance
            """,
            (blob, k),
        ).fetchall()
        return [
            {
                "id": r[0],
                "kind": r[1],
                "content": r[2],
                "task_id": r[3],
                "created_at": r[4],
                "distance": r[5],
            }
            for r in rows
        ]

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, kind, content, task_id, created_at FROM memory "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "id": r[0],
                "kind": r[1],
                "content": r[2],
                "task_id": r[3],
                "created_at": r[4],
            }
            for r in rows
        ]

    def delete(self, memory_id: int) -> bool:
        cur = self._conn.execute("DELETE FROM memory WHERE id = ?", (memory_id,))
        try:
            self._conn.execute("DELETE FROM vec_memory WHERE rowid = ?", (memory_id,))
        except sqlite3.OperationalError:
            pass
        self._conn.commit()
        return cur.rowcount > 0

    def stats(self) -> dict[str, Any]:
        row = self._conn.execute("SELECT COUNT(*) FROM memory").fetchone()
        return {"count": int(row[0]) if row else 0}

    def close(self) -> None:
        self._conn.close()


def extract_remember_content(text: str) -> str | None:
    """If *text* asks to remember something, return the content to store."""
    if "记住" not in text and "以后" not in text:
        return None
    m = re.search(r"(?:记住|以后)[:：\s]*(.+)$", text.strip(), re.DOTALL)
    if not m:
        return text.strip()
    content = m.group(1).strip()
    return content or text.strip()
