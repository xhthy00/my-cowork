"""
L5 Observability layer: trace bus and structured logging.

TraceBus emits events consumed by SSE routes and the UI.
configure_logger provides secret-redacted structured logging.
"""

from app.observability.logger import configure_logger, redact
from app.observability.trace import TraceBus
from app.observability.trace_store import TraceStore

__all__ = ["TraceBus", "TraceStore", "configure_logger", "redact"]
