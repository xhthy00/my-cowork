"""In-process event bus for channel SSE (pairing / status / user-authorized)."""

from __future__ import annotations

import asyncio
from typing import Any


class ChannelBus:
    def __init__(self) -> None:
        self._subs: list[asyncio.Queue[dict[str, Any]]] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def emit(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        event = {"type": event_type, **(payload or {})}
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(self._put_all, event)
        else:
            self._put_all(event)

    def _put_all(self, event: dict[str, Any]) -> None:
        for q in list(self._subs):
            try:
                q.put_nowait(event)
            except Exception:  # noqa: BLE001
                pass

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subs.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        if q in self._subs:
            self._subs.remove(q)
