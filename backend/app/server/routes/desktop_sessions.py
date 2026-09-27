"""Desktop conversation persistence and legacy localStorage import."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/desktop/sessions")


class Snapshot(BaseModel):
    sessions: list[dict[str, Any]] = Field(default_factory=list)
    activeId: str | None = None
    messagesById: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    spaces: list[dict[str, Any]] = Field(default_factory=list)
    activeSpaceId: str | None = None


@router.get("")
def get_sessions(request: Request) -> dict[str, Any]:
    store = getattr(request.app.state, "desktop_sessions", None)
    return {"snapshot": store.load() if store is not None else None}


@router.put("")
def put_sessions(body: Snapshot, request: Request) -> dict[str, bool]:
    store = getattr(request.app.state, "desktop_sessions", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Session storage unavailable")
    store.save(body.model_dump())
    return {"ok": True}
