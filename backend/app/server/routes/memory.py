"""Persistent memory management and live saving preferences."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.memory.scoped import project_memory_key

router = APIRouter()


class MemoryCreate(BaseModel):
    content: str = Field(..., min_length=1)
    summary: str = ""
    scope: str = "global"
    workspace: str | None = None
    project_id: str | None = None
    kind: str = "note"  # accepted for existing clients
    task_id: str | None = None


class MemoryUpdate(BaseModel):
    content: str = Field(..., min_length=1)
    summary: str = ""


class SettingsUpdate(BaseModel):
    enabled: bool | None = None
    user_rules: str | None = None


def _store(request: Request):
    store = getattr(request.app.state, "long_term", None)
    if store is None:
        raise HTTPException(status_code=503, detail="memory store unavailable")
    return store


@router.get("/api/memory/settings")
def get_settings(request: Request) -> dict[str, object]:
    settings = getattr(request.app.state, "memory_settings", None)
    return settings.snapshot() if settings is not None else {"enabled": True, "user_rules": ""}


@router.put("/api/memory/settings")
def update_settings(body: SettingsUpdate, request: Request) -> dict[str, object]:
    settings = getattr(request.app.state, "memory_settings", None)
    if settings is None:
        raise HTTPException(status_code=503, detail="memory settings unavailable")
    return settings.update(enabled=body.enabled, user_rules=body.user_rules)


@router.get("/api/memory/list")
def list_memory(request: Request, limit: int = 50, workspace: str | None = None) -> dict[str, Any]:
    store = _store(request)
    key = project_memory_key(workspace) if workspace else None
    return {"items": store.list_memories(workspace=key, all_scopes=not bool(workspace), limit=limit)}


@router.get("/api/memory")
def search_memory(request: Request, q: str = "", k: int = 10,
                  workspace: str | None = None) -> dict[str, Any]:
    store = _store(request)
    key = project_memory_key(workspace) if workspace else None
    return {"items": store.list_memories(workspace=key, all_scopes=not bool(workspace), q=q, limit=k)}


@router.get("/api/memory/stats")
def memory_stats(request: Request) -> dict[str, Any]:
    return {"count": len(_store(request).list_memories(all_scopes=True))}


@router.post("/api/memory")
def create_memory(body: MemoryCreate, request: Request) -> dict[str, Any]:
    store = _store(request)
    key = project_memory_key(body.workspace, body.project_id)
    try:
        item = store.remember(body.content, scope=body.scope,
                              workspace=key, summary=body.summary)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": item["id"], "ok": True, "item": item}


@router.patch("/api/memory/{memory_id}")
def update_memory(memory_id: int, body: MemoryUpdate, request: Request) -> dict[str, Any]:
    try:
        item = _store(request).update_memory(memory_id, body.content, summary=body.summary)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="memory not found")
    return {"ok": True, "item": item}


@router.delete("/api/memory/{memory_id}")
def delete_memory(memory_id: int, request: Request) -> dict[str, Any]:
    if not _store(request).forget_memory(memory_id):
        raise HTTPException(status_code=404, detail="memory not found")
    return {"ok": True}


@router.delete("/api/memory")
def delete_all_memory(request: Request) -> dict[str, Any]:
    return {"ok": True, "deleted": _store(request).forget_all_memories()}
