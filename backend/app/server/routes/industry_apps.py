"""Industry application package management API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.industry_apps.package import (
    AppPackageError,
    disable_app,
    enable_app,
    inspect_zip,
    install_zip,
    list_installed,
    rollback_app,
)

router = APIRouter()


async def _zip_body(request: Request) -> bytes:
    raw = await request.body()
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="ZIP exceeds 50 MiB")
    return raw


@router.get("/api/industry-apps")
async def apps_list() -> dict:
    return {"apps": list_installed()}


@router.post("/api/industry-apps/inspect")
async def apps_inspect(request: Request) -> dict:
    try:
        return inspect_zip(await _zip_body(request)).public()
    except AppPackageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/industry-apps/install")
async def apps_install(request: Request) -> dict:
    raise HTTPException(status_code=409, detail="请使用桌面应用管理菜单完成安装和安全切换")


@router.post("/api/industry-apps/{app_id}/disable")
async def apps_disable(app_id: str) -> dict:
    try:
        return disable_app(app_id)
    except AppPackageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/industry-apps/{app_id}/enable")
async def apps_enable(app_id: str) -> dict:
    try:
        return enable_app(app_id)
    except AppPackageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/industry-apps/{app_id}/rollback")
async def apps_rollback(app_id: str) -> dict:
    try:
        return rollback_app(app_id)
    except AppPackageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
