"""OfficeCLI status / install / watch preview HTTP API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.tools.officecli.install import install_officecli
from app.tools.officecli.resolve import resolve_officecli

router = APIRouter()


class PreviewBody(BaseModel):
    file_path: str = Field(..., min_length=1)
    workspace: str | None = None


def _watch_manager(request: Request):
    mgr = getattr(request.app.state, "officecli_watch", None)
    if mgr is None:
        from app.tools.officecli.watch_manager import WatchManager

        mgr = WatchManager()
        request.app.state.officecli_watch = mgr
    return mgr


@router.get("/api/officecli/status")
async def officecli_status() -> dict[str, Any]:
    path = resolve_officecli()
    if path is None:
        return {"status": "missing", "path": None, "error_code": "OFFICECLI_NOT_FOUND"}
    return {"status": "ready", "path": str(path), "error_code": None}


@router.post("/api/officecli/install")
async def officecli_install() -> dict[str, Any]:
    return install_officecli()


@router.post("/api/ppt-preview/start")
@router.post("/api/word-preview/start")
@router.post("/api/excel-preview/start")
async def preview_start(body: PreviewBody, request: Request) -> dict[str, Any]:
    return _watch_manager(request).start(body.file_path)


@router.post("/api/ppt-preview/stop")
@router.post("/api/word-preview/stop")
@router.post("/api/excel-preview/stop")
async def preview_stop(body: PreviewBody, request: Request) -> dict[str, Any]:
    return _watch_manager(request).stop(body.file_path)
