"""Persist explicit directory permissions; bindings remain a separate source."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/admin/whitelist", tags=["permissions"])


class WhitelistBody(BaseModel):
    paths: list[str]


def _guard(request: Request):
    guard = getattr(request.app.state, "path_guard", None)
    if guard is None:
        raise HTTPException(503, "目录权限服务尚未就绪")
    return guard


@router.get("")
def get_whitelist(request: Request):
    guard = _guard(request)
    return {"paths": guard.get_whitelist(), "workspace_paths": guard.workspace_paths()}


@router.post("")
def save_whitelist(body: WhitelistBody, request: Request):
    guard = _guard(request)
    try:
        guard.save_whitelist(body.paths)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(500, "目录权限保存失败，请检查存储位置后重试") from exc
    return get_whitelist(request)
