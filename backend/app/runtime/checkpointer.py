"""LangGraph checkpointer factory (MemorySaver or async SQLite)."""

from __future__ import annotations

import asyncio
import concurrent.futures
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import MemorySaver


def _open_async_sqlite(db_path: Path) -> Any:
    """Open AsyncSqliteSaver on a fresh event loop (thread-safe)."""
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    async def _open() -> Any:
        conn = await aiosqlite.connect(str(db_path))
        saver = AsyncSqliteSaver(conn)
        await saver.setup()
        return saver

    return asyncio.run(_open())


def get_checkpointer(
    db_path: str | Path | None = None,
    *,
    sync: bool = False,
) -> Any:
    """Return a checkpointer.

    - ``db_path is None`` → in-memory ``MemorySaver`` (tests / ephemeral).
    - ``sync=True`` → sync ``SqliteSaver`` (sync ``invoke`` / unit tests only).
    - otherwise → ``AsyncSqliteSaver`` at *db_path* (required for ``astream``).
    """
    if db_path is None:
        return MemorySaver()

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if sync:
        import sqlite3

        from langgraph.checkpoint.sqlite import SqliteSaver

        conn = sqlite3.connect(str(path), check_same_thread=False)
        return SqliteSaver(conn)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _open_async_sqlite(path)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_open_async_sqlite, path).result(timeout=30)


def get_latest_state(checkpointer: Any, thread_id: str) -> dict[str, Any] | None:
    """Read the latest checkpointed state for *thread_id*, or None."""
    config = {"configurable": {"thread_id": thread_id}}
    # Prefer sync get_tuple when available (AsyncSqliteSaver exposes it).
    get_tuple = getattr(checkpointer, "get_tuple", None)
    if get_tuple is None:
        return None
    tup = get_tuple(config)
    if tup is None:
        return None
    checkpoint = tup.checkpoint
    return checkpoint.get("channel_values") if checkpoint else None
