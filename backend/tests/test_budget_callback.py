"""Tests for live LLM token budget callback."""

from __future__ import annotations

from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from app.llm import budget_callback as budget_callback_mod
from app.llm.budget_callback import BudgetTokenCallback, instrument_model_for_budget
from app.observability.trace import TraceBus
from app.runtime.budget import Budget
from app.runtime.budget_context import (
    BudgetRuntime,
    context_window_limit,
    get_budget_runtime,
    record_llm_tokens,
    reset_budget_runtime,
    set_budget_runtime,
)


class TestContextWindowLimit:
    def test_default_ignores_task_budget_env(self, monkeypatch):
        monkeypatch.delenv("MY_COWORK_CONTEXT_LIMIT", raising=False)
        monkeypatch.delenv("MY_COWORK_MAX_TOKENS", raising=False)
        assert context_window_limit() == 200_000

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("MY_COWORK_CONTEXT_LIMIT", "131072")
        monkeypatch.setenv("MY_COWORK_MAX_TOKENS", "50000")
        assert context_window_limit() == 131072


class TestRecordLlmTokens:
    def test_emit_budget_update(self, monkeypatch):
        monkeypatch.delenv("MY_COWORK_CONTEXT_LIMIT", raising=False)
        bus = TraceBus()
        events: list[dict] = []
        bus.subscribe(events.append)
        budget = Budget(max_steps=10, max_total_tokens=100_000)
        token = set_budget_runtime(
            BudgetRuntime(task_id="t1", bus=bus, budget=budget)
        )
        try:
            record_llm_tokens(1200)
            assert budget.tokens == 1200
            assert any(
                e.get("type") == "budget.update"
                and e.get("tokens") == 1200
                and e.get("max_tokens") == 100_000
                and e.get("context_limit") == 200_000
                for e in events
            )
        finally:
            reset_budget_runtime(token)
            assert get_budget_runtime() is None

    def test_noop_without_runtime(self):
        record_llm_tokens(500)  # must not raise


class TestBudgetTokenCallback:
    def test_counts_prompt_and_completion_without_usage(self, monkeypatch):
        monkeypatch.setattr(
            budget_callback_mod, "count_tokens", lambda texts: max(1, len(str(texts)) // 4)
        )
        bus = TraceBus()
        events: list[dict] = []
        bus.subscribe(events.append)
        budget = Budget(max_steps=10, max_total_tokens=100_000)
        token = set_budget_runtime(
            BudgetRuntime(task_id="t2", bus=bus, budget=budget)
        )
        cb = BudgetTokenCallback()
        run_id = uuid4()
        try:
            cb.on_chat_model_start(
                {},
                [[HumanMessage(content="hello world from user")]],
                run_id=run_id,
            )
            result = LLMResult(
                generations=[
                    [ChatGeneration(message=AIMessage(content="assistant reply here"))]
                ]
            )
            cb.on_llm_end(result, run_id=run_id)
            assert budget.tokens > 0
            assert any(e.get("type") == "budget.update" for e in events)
        finally:
            reset_budget_runtime(token)

    def test_prefers_provider_usage(self, monkeypatch):
        monkeypatch.delenv("MY_COWORK_CONTEXT_LIMIT", raising=False)
        bus = TraceBus()
        events: list[dict] = []
        bus.subscribe(events.append)
        budget = Budget(max_steps=10, max_total_tokens=100_000)
        token = set_budget_runtime(
            BudgetRuntime(task_id="t3", bus=bus, budget=budget)
        )
        cb = BudgetTokenCallback()
        run_id = uuid4()
        try:
            cb.on_chat_model_start(
                {},
                [[HumanMessage(content="x" * 1000)]],
                run_id=run_id,
            )
            result = LLMResult(
                generations=[[ChatGeneration(message=AIMessage(content="y"))]],
                llm_output={"token_usage": {"total_tokens": 42}},
            )
            cb.on_llm_end(result, run_id=run_id)
            assert budget.tokens == 42
            ctx = [e for e in events if e.get("type") == "budget.update"][-1]
            assert ctx["max_tokens"] == 100_000
            assert ctx["context_limit"] == 200_000
            assert ctx["context_tokens"] > 0
        finally:
            reset_budget_runtime(token)


    def test_preview_on_start_and_stream_does_not_consume(self, monkeypatch):
        monkeypatch.setattr(
            budget_callback_mod, "count_tokens", lambda texts: max(1, len(str(texts)) // 4)
        )
        bus = TraceBus()
        events: list[dict] = []
        bus.subscribe(events.append)
        budget = Budget(max_steps=10, max_total_tokens=100_000)
        token = set_budget_runtime(
            BudgetRuntime(task_id="t4", bus=bus, budget=budget)
        )
        cb = BudgetTokenCallback()
        run_id = uuid4()
        try:
            cb.on_chat_model_start(
                {},
                [[HumanMessage(content="hello world from user")]],
                run_id=run_id,
            )
            assert budget.tokens == 0
            previews = [e for e in events if e.get("type") == "budget.update"]
            assert previews
            assert previews[0]["tokens"] > 0
            cb.on_llm_new_token("assistant reply here", run_id=run_id)
            streamed = [e for e in events if e.get("type") == "budget.update"]
            assert streamed[-1]["tokens"] >= previews[0]["tokens"]
            assert streamed[-1]["output_tokens"] > 0
            assert budget.tokens == 0
        finally:
            reset_budget_runtime(token)


class TestInstrumentModel:
    def test_appends_callback_once(self):
        class _M:
            callbacks = None

        m = _M()
        out = instrument_model_for_budget(m)
        assert out is m
        assert budget_callback_mod.BUDGET_TOKEN_CALLBACK in m.callbacks
        instrument_model_for_budget(m)
        assert m.callbacks.count(budget_callback_mod.BUDGET_TOKEN_CALLBACK) == 1
