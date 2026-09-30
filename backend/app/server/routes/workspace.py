"""Local Space workspace bind / overlay APIs (Eigent Brain subset, no cloud)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.workspace.overlay import get_overlay_store, refresh_project_workdir
from app.workspace.resolver import get_workspace_resolver

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


class BindBody(BaseModel):
    space_id: str
    root_path: str


class ScratchBody(BaseModel):
    space_id: str


class UnbindBody(BaseModel):
    space_id: str


class OverlayActionBody(BaseModel):
    overlay_ids: list[str] | None = None


@router.get("/current")
def workspace_current(space_id: str | None = None) -> dict[str, Any]:
    resolver = get_workspace_resolver()
    bindings = resolver.store.list_bindings()
    if space_id:
        b = resolver.store.get_binding(space_id)
        return {"binding": asdict(b) if b else None}
    return {"bindings": [asdict(b) for b in bindings]}


@router.post("/bind")
def workspace_bind(body: BindBody) -> dict[str, Any]:
    try:
        binding = get_workspace_resolver().ensure_space_binding(
            body.space_id, body.root_path
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        from app.tools.builtin.fs import get_guard

        get_guard().add_whitelist(binding.workspace_root)
    except Exception:
        pass
    return {"binding": asdict(binding)}


@router.post("/scratch")
def workspace_scratch(body: ScratchBody) -> dict[str, Any]:
    binding = get_workspace_resolver().ensure_scratch_binding(body.space_id)
    try:
        from app.tools.builtin.fs import get_guard

        get_guard().add_whitelist(binding.workspace_root)
    except Exception:
        pass
    return {"binding": asdict(binding)}


@router.delete("/{space_id}")
def workspace_unbind(space_id: str) -> dict[str, Any]:
    get_workspace_resolver().store.delete_binding(space_id)
    return {"ok": True, "space_id": space_id}


@router.post("/{space_id}/projects/{project_id}/refresh")
def workspace_refresh(space_id: str, project_id: str) -> dict[str, Any]:
    try:
        snapshot_id = refresh_project_workdir(space_id, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    get_overlay_store().discard_overlays(space_id, project_id)
    return {"ok": True, "base_snapshot_id": snapshot_id}


@router.get("/{space_id}/projects/{project_id}/overlays")
def workspace_list_overlays(space_id: str, project_id: str) -> dict[str, Any]:
    rows = get_overlay_store().list_overlays(space_id, project_id)
    return {"overlays": [asdict(r) for r in rows]}


@router.post("/{space_id}/projects/{project_id}/apply")
def workspace_apply(
    space_id: str, project_id: str, body: OverlayActionBody | None = None
) -> dict[str, Any]:
    ids = body.overlay_ids if body else None
    try:
        result = get_overlay_store().apply_overlays(space_id, project_id, ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.post("/{space_id}/projects/{project_id}/discard")
def workspace_discard(
    space_id: str, project_id: str, body: OverlayActionBody | None = None
) -> dict[str, Any]:
    ids = body.overlay_ids if body else None
    removed = get_overlay_store().discard_overlays(space_id, project_id, ids)
    return {"ok": True, "removed": removed}
