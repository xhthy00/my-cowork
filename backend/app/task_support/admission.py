"""Count actual execution, including synchronous workers after await cancellation."""
from __future__ import annotations

import asyncio
import threading
from contextlib import contextmanager
from contextvars import ContextVar

_lease = ContextVar("work_lease", default=None)


class MaintenanceBusy(RuntimeError):
    def __init__(self):
        super().__init__("应用正在更新，稍后可继续")


class Admission:
    def __init__(self, *, paused=False):
        self._lock = threading.RLock()
        self.paused = paused
        self._work = {}
        self._next = 0

    def acquire(self, label="任务"):
        with self._lock:
            parent = _lease.get()
            if self.paused and not (parent and parent[0] is self and parent[1] in self._work):
                raise MaintenanceBusy()
            self._next += 1
            self._work[self._next] = label
            return self._next

    def release(self, lease):
        with self._lock:
            self._work.pop(lease, None)

    @contextmanager
    def work(self, label="任务", lease=None):
        lease = self.acquire(label) if lease is None else lease
        token = _lease.set((self, lease))
        try:
            yield
        finally:
            _lease.reset(token)
            self.release(lease)

    def pause(self):
        with self._lock:
            self.paused = True
            return self.status()

    def resume(self):
        with self._lock:
            self.paused = False

    def status(self):
        with self._lock:
            return {"paused": self.paused, "active": len(self._work), "tasks": list(self._work.values())}

    async def thread(self, callback, *args):
        # Reserve before submission; release in the worker, never in the
        # cancelled awaiter. Shield also keeps a queued worker from vanishing.
        lease = self.acquire("插件工具")
        def run():
            with self.work("插件工具", lease):
                return callback(*args)
        task = asyncio.create_task(asyncio.to_thread(run))
        task.add_done_callback(lambda done: done.exception() if not done.cancelled() else None)
        return await asyncio.shield(task)
