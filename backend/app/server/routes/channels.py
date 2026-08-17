"""Channel REST + SSE — AionUi /api/channel/* contract."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.server.channels.manager import ChannelError, ChannelManager

router = APIRouter()


def _mgr(request: Request) -> ChannelManager:
    mgr = getattr(request.app.state, "channels", None)
    if mgr is None:
        raise HTTPException(status_code=503, detail="渠道服务未启动")
    return mgr


class EnableBody(BaseModel):
    plugin_id: str
    config: dict[str, Any] = Field(default_factory=dict)


class PluginIdBody(BaseModel):
    plugin_id: str


class TestBody(BaseModel):
    plugin_id: str
    token: str = ""
    extra_config: dict[str, Any] | None = None


class CodeBody(BaseModel):
    code: str


class UserBody(BaseModel):
    user_id: str


class AssistantBody(BaseModel):
    assistant_id: str | None = None
    assistant: dict[str, Any] | None = None


class DefaultModelBody(BaseModel):
    id: str | None = None
    use_model: str | None = None
    default_model: dict[str, Any] | None = None


@router.get("/api/channel/plugins")
def get_plugins(request: Request) -> list[dict[str, Any]]:
    return _mgr(request).list_plugins()


@router.post("/api/channel/plugins/enable")
def enable_plugin(request: Request, body: EnableBody) -> dict[str, Any]:
    try:
        return _mgr(request).enable_plugin(body.plugin_id, body.config)
    except ChannelError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/api/channel/plugins/disable")
def disable_plugin(request: Request, body: PluginIdBody) -> dict[str, Any]:
    try:
        return _mgr(request).disable_plugin(body.plugin_id)
    except ChannelError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/api/channel/plugins/test")
def test_plugin(request: Request, body: TestBody) -> dict[str, Any]:
    extra = body.extra_config or {}
    return _mgr(request).test_plugin(body.plugin_id, extra)


@router.get("/api/channel/pairings")
def get_pairings(request: Request) -> list[dict[str, Any]]:
    return _mgr(request).list_pairings()


@router.post("/api/channel/pairings/approve")
def approve_pairing(request: Request, body: CodeBody) -> dict[str, Any]:
    try:
        return _mgr(request).approve_pairing(body.code)
    except ChannelError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/api/channel/pairings/reject")
def reject_pairing(request: Request, body: CodeBody) -> dict[str, Any]:
    return _mgr(request).reject_pairing(body.code)


@router.get("/api/channel/users")
def get_users(request: Request) -> list[dict[str, Any]]:
    return _mgr(request).list_users()


@router.post("/api/channel/users/revoke")
def revoke_user(request: Request, body: UserBody) -> dict[str, Any]:
    try:
        return _mgr(request).revoke_user(body.user_id)
    except ChannelError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/api/channel/settings/{platform}")
def get_settings(request: Request, platform: str) -> dict[str, Any]:
    return _mgr(request).get_settings(platform)


@router.put("/api/channel/settings/{platform}/assistant")
def set_assistant(request: Request, platform: str, body: AssistantBody) -> dict[str, Any]:
    assistant_id = body.assistant_id or (body.assistant or {}).get("assistant_id") or ""
    if not assistant_id:
        raise HTTPException(status_code=400, detail="assistant_id required")
    return _mgr(request).set_assistant(platform, str(assistant_id))


@router.put("/api/channel/settings/{platform}/default-model")
def set_default_model(request: Request, platform: str, body: DefaultModelBody) -> dict[str, Any]:
    nested = body.default_model or {}
    model_id = body.id or nested.get("id") or ""
    use_model = body.use_model or nested.get("use_model") or ""
    if not model_id or not use_model:
        raise HTTPException(status_code=400, detail="id and use_model required")
    return _mgr(request).set_default_model(platform, str(model_id), str(use_model))


@router.post("/api/channel/settings/sync")
def sync_settings(request: Request, body: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"ok": True}


@router.get("/api/channel/stream")
async def channel_stream(request: Request) -> StreamingResponse:
    mgr = _mgr(request)
    queue = mgr.bus.subscribe()

    async def gen():
        try:
            yield f"data: {json.dumps({'type': 'channel.hello'})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            mgr.bus.unsubscribe(queue)

    return StreamingResponse(gen(), media_type="text/event-stream")
