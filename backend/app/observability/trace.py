"""In-memory trace bus with delivery on its owning event-loop thread."""

import asyncio
import threading
from typing import Any, Callable


def _runtime_task_id() -> str | None:
    """Stamp emits with the in-flight task when callers omit ``task_id``."""
    try:
        from app.runtime.todo_context import get_todo_runtime

        todo = get_todo_runtime()
        if todo is not None and getattr(todo, "task_id", None):
            return str(todo.task_id)
    except Exception:
        pass
    try:
        from app.runtime.budget_context import get_budget_runtime

        budget = get_budget_runtime()
        if budget is not None and getattr(budget, "task_id", None):
            return str(budget.task_id)
    except Exception:
        pass
    return None


class TraceBus:
    """Deliver synchronously on the owner; queue worker events to its loop."""

    def __init__(self) -> None:
        self._subs: list[Callable[[dict[str, Any]], None]] = []
        self.tool_metadata: dict[str, dict[str, str]] = {}
        self._owner_thread = threading.get_ident()
        self._loop: asyncio.AbstractEventLoop | None = None
        try:
            self.bind_loop()
        except RuntimeError:
            # The production stack is assembled before uvicorn starts its loop.
            pass

    def bind_loop(self) -> None:
        """Bind on the owner before dispatching tools into worker threads."""
        if threading.get_ident() != self._owner_thread:
            raise RuntimeError("TraceBus must be bound on its owning thread")
        loop = asyncio.get_running_loop()
        if self._loop is not None and self._loop is not loop and self._loop.is_running():
            raise RuntimeError("TraceBus is already bound to another running loop")
        self._loop = loop

    def subscribe(self, callback: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
        """Register a callback. Returns an unsubscribe callable."""
        self._subs.append(callback)

        def unsubscribe() -> None:
            self._subs.remove(callback)

        return unsubscribe

    def emit(self, event: dict[str, Any]) -> None:
        """Deliver event to all subscribers on the owner thread.

        A failing subscriber does not block delivery to the remaining ones.
        Concurrent tasks share one bus; ``task_id`` is filled from the
        current runtime context when the payload omitted it.
        """
        stamped = event
        if not event.get("task_id"):
            tid = _runtime_task_id()
            if tid:
                stamped = {**event, "task_id": tid}
                payload = stamped.get("payload")
                if isinstance(payload, dict) and "task_id" not in payload:
                    stamped["payload"] = {**payload, "task_id": tid}
        # Stamp task context before leaving the tool's worker thread. SQLite
        # subscribers and asyncio consumers must run on the backend thread.
        if threading.get_ident() != self._owner_thread:
            if self._loop is None or not self._loop.is_running():
                raise RuntimeError("TraceBus has no running owner loop for worker events")
            self._loop.call_soon_threadsafe(self._deliver, stamped)
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            self.bind_loop()
        self._deliver(stamped)

    def _deliver(self, event: dict[str, Any]) -> None:
        for callback in tuple(self._subs):
            try:
                callback(event)
            except Exception:
                # Swallow subscriber errors to keep the bus resilient. If a
                # logger is available later, log the traceback here.
                pass
