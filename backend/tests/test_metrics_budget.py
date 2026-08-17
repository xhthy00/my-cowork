"""Tests for MetricsStore and 200k budget hard stop."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.observability.metrics import MetricsStore
from app.observability.trace import TraceBus
from app.runtime.budget import Budget, BudgetExhausted


def test_budget_130k_ok_200k_stops():
    budget = Budget(max_steps=10**9, max_total_tokens=200_000)
    budget.consume_tokens(130_000)
    assert budget.exhausted is False
    budget.consume_tokens(70_000)  # exactly 200k still ok (>)
    assert budget.tokens == 200_000
    with pytest.raises(BudgetExhausted):
        budget.consume_tokens(1)
    assert budget.exhausted is True


def test_metrics_daily_exceeded(tmp_path: Path):
    store = MetricsStore(tmp_path / "u.db")
    bus = TraceBus()
    events: list[dict] = []
    bus.subscribe(lambda e: events.append(e))

    day = datetime(2024, 6, 1, tzinfo=timezone.utc)
    store.log("t1", tokens_in=100, usd=6.0, at=day.timestamp() + 100)
    store.log("t2", tokens_in=100, usd=5.0, at=day.timestamp() + 200)
    assert store.check_daily_threshold(10.0, bus, day=day) is True
    assert any(e["type"] == "metrics.daily_exceeded" for e in events)
    store.close()
