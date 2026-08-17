"""Memory CRUD HTTP API (sqlite-vec LongTermStore)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()


class MemoryCreate(BaseModel):
    content: str = Field(..., min_length=1)
    kind: str = "note"
    task_id: str | None = None


@router.get("/api/memory/list")
async def list_memory(request: Request, limit: int = 50) -> dict[str, Any]:
    store = getattr(request.app.state, "long_term", None)
    if store is None:
        return {"items": []}
    return {"items": store.list_recent(limit=limit)}


@router.get("/api/memory")
async def search_memory(request: Request, q: str = "", k: int = 10) -> dict[str, Any]:
    store = getattr(request.app.state, "long_term", None)
    if store is None:
        return {"items": []}
    if not q.strip():
        return {"items": store.list_recent(limit=k)}
    return {"items": store.query(q, k=k)}


@router.post("/api/memory")
async def create_memory(body: MemoryCreate, request: Request) -> dict[str, Any]:
    store = getattr(request.app.state, "long_term", None)
    if store is None:
        raise HTTPException(status_code=503, detail="memory store unavailable")
    row_id = store.write(body.content, kind=body.kind, task_id=body.task_id)
    return {"id": row_id, "ok": True}


@router.delete("/api/memory/{memory_id}")
async def delete_memory(memory_id: int, request: Request) -> dict[str, Any]:
    store = getattr(request.app.state, "long_term", None)
    if store is None:
        raise HTTPException(status_code=503, detail="memory store unavailable")
    ok = store.delete(memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}


@router.get("/api/memory/stats")
async def memory_stats(request: Request) -> dict[str, Any]:
    store = getattr(request.app.state, "long_term", None)
    if store is None:
        return {"count": 0}
    return store.stats()
