"""L6 long-term vector memory backed by SQLite + sqlite-vec."""

from __future__ import annotations

import re
import sqlite3
import struct
import threading
import time
from pathlib import Path
from typing import Any, Callable

import sqlite_vec

EmbedFn = Callable[[str], list[float]]

_DEFAULT_DIM = 64


def _load_sqlite_vec(conn: sqlite3.Connection) -> bool:
    """Load sqlite-vec. Returns False when this Python/sqlite cannot load extensions.

    python.org / some uv standalone macOS builds omit Connection.enable_load_extension.
    """
    enable = getattr(conn, "enable_load_extension", None)
    load_ext = getattr(conn, "load_extension", None)
    if not callable(enable) or not callable(load_ext):
        return False
    try:
        enable(True)
        try:
            load_ext(sqlite_vec.loadable_path())
        finally:
            enable(False)
        return True
    except Exception:
        try:
            enable(False)
        except Exception:
            pass
        return False


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
        self._lock = threading.RLock()
        self.dim = dim
        self.semantic_enabled = embed_fn is not None
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.vec_ready = _load_sqlite_vec(self._conn)
        if not self.vec_ready:
            self.semantic_enabled = False
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
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS persistent_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope TEXT NOT NULL CHECK(scope IN ('global', 'workspace')),
                workspace TEXT,
                content TEXT NOT NULL,
                summary TEXT,
                created_at REAL NOT NULL,
                legacy_id INTEGER UNIQUE
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_persistent_memories_scope "
            "ON persistent_memories(scope, workspace, id)"
        )
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_snapshots (
                session_id TEXT PRIMARY KEY,
                block TEXT NOT NULL
            )
        """)
        self._conn.execute("CREATE TABLE IF NOT EXISTS memory_meta (key TEXT PRIMARY KEY, value TEXT)")
        if self._conn.execute("SELECT 1 FROM memory_meta WHERE key='scoped_migration'").fetchone() is None:
            # One-time import. A deleted memory must stay deleted on later launches.
            self._conn.execute("""
                INSERT OR IGNORE INTO persistent_memories
                    (scope, workspace, content, summary, created_at, legacy_id)
                SELECT 'global', NULL, content, NULL, COALESCE(created_at, 0), id
                FROM memory WHERE kind IN ('note', 'user_note', 'pref', 'fact')
                  AND COALESCE(task_id, '') = ''
            """)
            self._conn.execute(
                "INSERT INTO memory_meta(key, value) VALUES ('scoped_migration', '1')"
            )
        if self._conn.execute("SELECT 1 FROM memory_meta WHERE key='scoped_migration_v2'").fetchone() is None:
            # Older imports may have treated task-specific notes as global.
            # Retain the data under a private task key instead of exposing it
            # to unrelated projects.
            self._conn.execute("""
                UPDATE persistent_memories
                SET scope='workspace',
                    workspace='project:' || (
                        SELECT task_id FROM memory WHERE memory.id=persistent_memories.legacy_id
                    )
                WHERE legacy_id IN (
                    SELECT id FROM memory WHERE COALESCE(task_id, '') != ''
                )
            """)
            self._conn.execute(
                "INSERT INTO memory_meta(key, value) VALUES ('scoped_migration_v2', '1')"
            )
        # vec0 virtual table — rowid aligns with memory.id
        if self.vec_ready:
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
        elif not self.semantic_enabled:
            return [0.0] * self.dim
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
        if self.vec_ready:
            try:
                self._conn.execute(
                    "INSERT INTO vec_memory(rowid, embedding) VALUES (?, ?)",
                    (rowid, blob),
                )
            except sqlite3.OperationalError:
                pass
        self._conn.commit()
        return rowid

    def query(self, text: str, k: int = 3) -> list[dict[str, Any]]:
        if not self.semantic_enabled or not self.vec_ready:
            return []
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

    def remember(self, content: str, *, scope: str = "workspace",
                 workspace: str | None = None, summary: str = "") -> dict[str, Any]:
        content = content.strip()
        if not content:
            raise ValueError("Memory content is required")
        if scope not in {"global", "workspace"}:
            raise ValueError("Memory scope must be global or workspace")
        if scope == "workspace" and not workspace:
            raise ValueError("Workspace memory requires a project")
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO persistent_memories(scope, workspace, content, summary, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (scope, workspace if scope == "workspace" else None, content,
                 summary.strip() or None, time.time()),
            )
            self._conn.commit()
            return self.get_memory(int(cursor.lastrowid)) or {}

    def get_memory(self, memory_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT id, scope, workspace, content, summary, created_at "
                "FROM persistent_memories WHERE id = ?", (memory_id,)
            ).fetchone()
        return dict(zip(("id", "scope", "workspace", "content", "summary", "created_at"), row)) if row else None

    def list_memories(self, *, workspace: str | None = None,
                      all_scopes: bool = False, q: str = "",
                      limit: int | None = None) -> list[dict[str, Any]]:
        sql = ("SELECT id, scope, workspace, content, summary, created_at "
               "FROM persistent_memories WHERE 1=1")
        args: list[Any] = []
        if not all_scopes:
            sql += " AND (scope = 'global'"
            if workspace:
                sql += " OR (scope = 'workspace' AND workspace = ?))"
                args.append(workspace)
            else:
                sql += ")"
        if q.strip():
            sql += " AND (content LIKE ? OR summary LIKE ?)"
            pattern = f"%{q.strip()}%"
            args.extend((pattern, pattern))
        sql += " ORDER BY id DESC"
        if limit is not None:
            sql += " LIMIT ?"
            args.append(max(1, min(int(limit), 1000)))
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        fields = ("id", "scope", "workspace", "content", "summary", "created_at")
        return [dict(zip(fields, row)) for row in rows]

    def update_memory(self, memory_id: int, content: str, *, summary: str = "") -> dict[str, Any] | None:
        if not content.strip():
            raise ValueError("Memory content is required")
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE persistent_memories SET content=?, summary=? WHERE id=?",
                (content.strip(), summary.strip() or None, memory_id),
            )
            self._conn.commit()
        return self.get_memory(memory_id) if cursor.rowcount else None

    def forget_memory(self, memory_id: int) -> bool:
        with self._lock:
            cursor = self._conn.execute("DELETE FROM persistent_memories WHERE id=?", (memory_id,))
            self._conn.commit()
        return bool(cursor.rowcount)

    def forget_all_memories(self) -> int:
        with self._lock:
            cursor = self._conn.execute("DELETE FROM persistent_memories")
            self._conn.commit()
        return int(cursor.rowcount)

    def prompt_block(self, *, workspace: str | None, session_id: str | None = None) -> str:
        """Freeze remembered knowledge for a session; new sessions see later edits."""
        from .scoped import render_memories

        if session_id:
            with self._lock:
                row = self._conn.execute(
                    "SELECT block FROM memory_snapshots WHERE session_id=?", (session_id,)
                ).fetchone()
            if row is not None:
                return str(row[0])
        settings = getattr(self, "memory_settings", None)
        rules = str(settings.snapshot()["user_rules"] or "").strip() if settings else ""
        parts = []
        if rules:
            parts.append("用户在设置中编写的长期规则（优先于学习到的记忆）：\n" + rules)
        items = self.list_memories(workspace=workspace)
        remembered = render_memories(items)
        if remembered:
            parts.append(remembered)
        block = "\n\n".join(parts)
        if session_id:
            with self._lock:
                self._conn.execute(
                    "INSERT OR IGNORE INTO memory_snapshots(session_id, block) VALUES (?, ?)",
                    (session_id, block),
                )
                self._conn.commit()
        return block


def extract_remember_content(text: str) -> str | None:
    """If *text* asks to remember something, return the content to store."""
    if "记住" not in text and "以后" not in text:
        return None
    m = re.search(r"(?:记住|以后)[:：\s]*(.+)$", text.strip(), re.DOTALL)
    if not m:
        return text.strip()
    content = m.group(1).strip()
    return content or text.strip()
