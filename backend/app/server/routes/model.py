"""Model connectivity validation (BYOK / local OpenAI-compatible)."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from app.llm import gateway

router = APIRouter()


class ValidateBody(BaseModel):
    provider: str
    model: str
    api_key: str = ""
    base_url: str | None = None


class ValidateResult(BaseModel):
    ok: bool
    error: str | None = None
    latency_ms: int | None = None


@router.post("/api/model/validate", response_model=ValidateResult)
async def validate_model(body: ValidateBody) -> dict[str, Any]:
    """Probe a provider with a short completion (Eigent-style validate)."""
    started = time.perf_counter()
    provider = body.provider.strip()
    model = body.model.strip()
    if not model:
        return {"ok": False, "error": "model is required", "latency_ms": 0}
    if provider not in gateway.PROVIDERS:
        return {
            "ok": False,
            "error": f"Unknown provider: {provider!r}",
            "latency_ms": 0,
        }

    kwargs: dict[str, Any] = {}
    if body.base_url and provider == "openai_compat":
        kwargs["base_url"] = body.base_url

    try:
        llm = gateway.create_model(provider, model, body.api_key, **kwargs)
        await llm.ainvoke([HumanMessage(content="ping")])
        ms = int((time.perf_counter() - started) * 1000)
        return {"ok": True, "error": None, "latency_ms": ms}
    except Exception as exc:  # noqa: BLE001 — surface provider errors to UI
        ms = int((time.perf_counter() - started) * 1000)
        return {"ok": False, "error": str(exc)[:500], "latency_ms": ms}
