"""Read-only trace event API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/api/trace/{task_id}")
async def get_trace(task_id: str, request: Request, limit: int = 500) -> dict[str, Any]:
    store = getattr(request.app.state, "trace_store", None)
    if store is None:
        return {"task_id": task_id, "events": []}
    return {"task_id": task_id, "events": store.list_for_task(task_id, limit=limit)}
