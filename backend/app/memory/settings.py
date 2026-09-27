"""Persistent user-owned memory settings, independent of learned memories."""

from __future__ import annotations

import json
import threading
from pathlib import Path


class MemorySettings:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raw = {}
            if not isinstance(raw, dict):
                raw = {}
            return {"enabled": bool(raw.get("enabled", True)),
                    "user_rules": str(raw.get("user_rules") or "")[:20_000]}

    @property
    def enabled(self) -> bool:
        return bool(self.snapshot()["enabled"])

    def update(self, *, enabled: bool | None = None,
               user_rules: str | None = None) -> dict[str, object]:
        with self._lock:
            data = self.snapshot()
            if enabled is not None:
                data["enabled"] = bool(enabled)
            if user_rules is not None:
                data["user_rules"] = user_rules[:20_000]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return data
