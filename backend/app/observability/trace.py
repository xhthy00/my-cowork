"""In-memory trace event bus."""

from typing import Any, Callable


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
        """
        for callback in self._subs:
            try:
                callback(event)
            except Exception:
                # Swallow subscriber errors to keep the bus resilient. If a
                # logger is available later, log the traceback here.
                pass
