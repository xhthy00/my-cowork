"""L5 usage metrics store + daily threshold alerts."""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class MetricsStore:
    """SQLite log of per-task token/cost usage."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                tokens_in INTEGER,
                tokens_out INTEGER,
                usd REAL,
                at REAL
            )
            """
        )
        self._conn.commit()

    def log(
        self,
        task_id: str,
        tokens_in: int,
        tokens_out: int = 0,
        usd: float = 0.0,
        at: float | None = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO usage_log(task_id, tokens_in, tokens_out, usd, at) VALUES (?,?,?,?,?)",
            (task_id, tokens_in, tokens_out, usd, at if at is not None else time.time()),
        )
        self._conn.commit()

    def daily_usd(self, day: datetime | None = None) -> float:
        day = day or datetime.now(timezone.utc)
        start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp()
        end = start + 86400
        row = self._conn.execute(
            "SELECT COALESCE(SUM(usd), 0) FROM usage_log WHERE at >= ? AND at < ?",
            (start, end),
        ).fetchone()
        return float(row[0] if row else 0.0)

    def check_daily_threshold(
        self,
        limit_usd: float,
        bus: Any,
        *,
        day: datetime | None = None,
    ) -> bool:
        """If today's spend exceeds *limit_usd*, emit ``metrics.daily_exceeded``."""
        total = self.daily_usd(day)
        if total <= limit_usd:
            return False
        bus.emit(
            {
                "type": "metrics.daily_exceeded",
                "usd": total,
                "limit_usd": limit_usd,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        return True

    def close(self) -> None:
        self._conn.close()
