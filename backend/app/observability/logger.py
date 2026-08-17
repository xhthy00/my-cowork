"""Structured logging with key redaction."""

import logging
from typing import Any

import structlog


SENSITIVE_KEY_PARTS = ("api_key", "authorization")


def redact(record: Any) -> Any:
    """Recursively redact values whose keys look like secrets."""
    if isinstance(record, dict):
        result: dict[Any, Any] = {}
        for key, value in record.items():
            if isinstance(key, str) and any(part in key.lower() for part in SENSITIVE_KEY_PARTS):
                result[key] = "***"
            else:
                result[key] = redact(value)
        return result
    if isinstance(record, list):
        return [redact(item) for item in record]
    return record


def _redact_processor(
    _logger: Any,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    return redact(event_dict)


def configure_logger(handlers: list[logging.Handler] | None = None) -> Any:
    """Return a structlog logger with secret redaction enabled."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            _redact_processor,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )

    stdlib_logger = logging.getLogger("my-cowork")
    stdlib_logger.setLevel(logging.DEBUG)

    if handlers is not None:
        for handler in handlers:
            stdlib_logger.addHandler(handler)

    return structlog.get_logger("my-cowork")
