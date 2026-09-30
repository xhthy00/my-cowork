"""Authenticated desktop lifecycle controls and request admission."""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import JSONResponse

from app.industry_apps.lifecycle import TERMINAL, operation
from app.industry_apps.package import app_root
from app.runtime.admission import MaintenanceBusy

router = APIRouter(prefix="/api/industry-apps/runtime")


class AdmissionMiddleware:
    def __init__(self, app, admission):
        self.app = app
        self.admission = admission

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] == "http" and (path == "/api/chat" or path.startswith("/api/apps/")):
            try:
                with self.admission.work("聊天" if path == "/api/chat" else "插件页面"):
                    await self.app(scope, receive, send)
            except MaintenanceBusy as exc:
                await JSONResponse({"detail": str(exc)}, status_code=503)(scope, receive, send)
        else:
            await self.app(scope, receive, send)


@router.get("")
async def status(request: Request):
    state = request.app.state
    return {**state.admission.status(), "generation": state.generation, "apps": state.industry_apps}


@router.post("/drain")
async def drain(request: Request):
    return request.app.state.admission.pause()


@router.post("/open")
async def open_runtime(request: Request):
    op = operation(app_root())
    if op and op["phase"] not in TERMINAL:
        raise HTTPException(409, "更新尚未完成")
    state = request.app.state
    state.admission.resume()
    scheduler = getattr(state, "automation_scheduler", None)
    if scheduler:
        scheduler.start()
    if not getattr(state, "channels_started", False):
        state.channels_started = True
        if os.environ.get("MY_COWORK_CHANNEL_AUTOSTART", "1") != "0" and not os.environ.get("PYTEST_CURRENT_TEST"):
            state.channels.restore_enabled()
    return await status(request)
