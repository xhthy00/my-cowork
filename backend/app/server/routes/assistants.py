"""Assistants HTTP API — minimal AionUi-shaped list/get."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.assistants import get_assistant, load_assistants

router = APIRouter()


def _path(request: Request):
    return getattr(request.app.state, "assistants_path", None)


@router.get("/api/assistants")
async def list_assistants(request: Request) -> dict[str, Any]:
    return {"assistants": load_assistants(_path(request))}


@router.get("/api/assistants/{assistant_id}")
async def assistant_detail(assistant_id: str, request: Request) -> dict[str, Any]:
    found = get_assistant(assistant_id, _path(request))
    if found is None:
        raise HTTPException(status_code=404, detail="assistant not found")
    return found
