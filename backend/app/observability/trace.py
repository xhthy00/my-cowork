"""In-memory trace event bus."""

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
    """Synchronous pub/sub event bus for trace events."""

    def __init__(self) -> None:
        self._subs: list[Callable[[dict[str, Any]], None]] = []

    def subscribe(self, callback: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
        """Register a callback. Returns an unsubscribe callable."""
        self._subs.append(callback)

        def unsubscribe() -> None:
            self._subs.remove(callback)

        return unsubscribe

    def emit(self, event: dict[str, Any]) -> None:
        """Deliver event to all subscribers.

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
        for callback in self._subs:
            try:
                callback(stamped)
            except Exception:
                # Swallow subscriber errors to keep the bus resilient. If a
                # logger is available later, log the traceback here.
                pass
