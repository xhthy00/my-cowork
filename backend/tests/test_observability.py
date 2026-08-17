import io
import logging

import pytest
import structlog

from app.observability.logger import configure_logger, redact
from app.observability.trace import TraceBus


class TestTraceBus:
    def test_subscriber_receives_emitted_event(self):
        bus = TraceBus()
        received = []

        def callback(event):
            received.append(event)

        bus.subscribe(callback)
        bus.emit({"type": "graph.step", "payload": {"node": "supervisor"}})

        assert len(received) == 1
        assert received[0]["type"] == "graph.step"

    def test_unsubscribe_stops_delivery(self):
        bus = TraceBus()
        received = []

        unsub = bus.subscribe(lambda e: received.append(e))
        unsub()
        bus.emit({"type": "graph.step"})

        assert received == []

    def test_multiple_subscribers_receive_event(self):
        bus = TraceBus()
        a, b = [], []
        bus.subscribe(lambda e: a.append(e))
        bus.subscribe(lambda e: b.append(e))
        bus.emit({"type": "tool.result"})

        assert len(a) == 1
        assert len(b) == 1

    def test_failing_subscriber_does_not_block_others(self):
        bus = TraceBus()
        received = []

        def failing_subscriber(_event):
            raise RuntimeError("boom")

        bus.subscribe(failing_subscriber)
        bus.subscribe(lambda e: received.append(e))
        bus.emit({"type": "tool.result"})

        assert len(received) == 1
        assert received[0]["type"] == "tool.result"


class TestRedact:
    def test_redacts_authorization_header(self):
        record = {"headers": {"Authorization": "Bearer secret-token"}}
        redacted = redact(record)
        assert redacted["headers"]["Authorization"] == "***"

    def test_redacts_api_key(self):
        record = {"api_key": "sk-12345", "other": "visible"}
        redacted = redact(record)
        assert redacted["api_key"] == "***"
        assert redacted["other"] == "visible"

    def test_redacts_nested_sensitive_keys(self):
        record = {"config": {"API_KEY": "secret"}, "safe": "ok"}
        redacted = redact(record)
        assert redacted["config"]["API_KEY"] == "***"
        assert redacted["safe"] == "ok"


class TestLogger:
    @pytest.fixture(autouse=True)
    def _reset_structlog(self):
        structlog.reset_defaults()
        yield
        structlog.reset_defaults()

    def test_logger_output_redacts_sensitive_values(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.set_name("test")
        logger = configure_logger(handlers=[handler])
        logger.info("request", headers={"Authorization": "Bearer xxx"})

        output = stream.getvalue()
        assert "***" in output
        assert "xxx" not in output
