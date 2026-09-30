"""Skills HTTP API — Eigent brain /skills shape (local yaml + skills-config)."""

from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.skills import config as skills_config
from app.skills.skillhub import SkillHubError, download_hub_skill, list_hub_skills

router = APIRouter()


class SkillPatch(BaseModel):
    enabled: bool | None = None
    scope: dict[str, Any] | None = None


class SkillImportBody(BaseModel):
    """Base64 zip payload — avoids python-multipart dependency."""

    zip_base64: str = Field(..., min_length=1)
    filename: str | None = None


class HubInstallBody(BaseModel):
    handle: str = Field(..., min_length=1, max_length=128)
    slug: str = Field(..., min_length=1, max_length=128)


def _hub_http_error(exc: SkillHubError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


# Not under /api/skills/{id}: GET /api/skills/hub is captured as skill_id="hub"
# (PATCH/DELETE only) and Starlette returns 405.
@router.get("/api/skillhub")
async def list_hub(
    keyword: str = "",
    category: str = "",
    sort_by: str = Query("score", alias="sortBy"),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, alias="pageSize", ge=1, le=50),
) -> dict[str, Any]:
    try:
        return await list_hub_skills(
            keyword=keyword,
            category=category,
            sort_by=sort_by,
            page=page,
            page_size=page_size,
        )
    except SkillHubError as exc:
        raise _hub_http_error(exc) from exc


@router.post("/api/skillhub/install")
async def install_hub(body: HubInstallBody, request: Request) -> dict[str, Any]:
    root = getattr(request.app.state, "skills_root", None)
    try:
        raw = await download_hub_skill(body.handle, body.slug)
        meta = skills_config.import_skill_zip(raw, root=root)
    except SkillHubError as exc:
        raise _hub_http_error(exc) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": meta.id, "name": meta.name, "description": meta.description}


@router.get("/api/skills")
async def list_skills(request: Request) -> dict[str, Any]:
    root = getattr(request.app.state, "skills_root", None)
    cfg_path = getattr(request.app.state, "skills_config_path", None)
    return {"skills": skills_config.list_skills_api(root=root, config_path=cfg_path)}


@router.patch("/api/skills/{skill_id}")
async def patch_skill(skill_id: str, body: SkillPatch, request: Request) -> dict[str, Any]:
    cfg_path = getattr(request.app.state, "skills_config_path", None)
    patch = body.model_dump(exclude_none=True)
    return skills_config.patch_skill_config(skill_id, patch, config_path=cfg_path)


@router.post("/api/skills/import")
async def import_skill(body: SkillImportBody, request: Request) -> dict[str, Any]:
    root = getattr(request.app.state, "skills_root", None)
    try:
        raw = base64.b64decode(body.zip_base64)
        meta = skills_config.import_skill_zip(raw, root=root)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": meta.id, "name": meta.name, "description": meta.description}


@router.delete("/api/skills/{skill_id}")
async def remove_skill(skill_id: str, request: Request) -> dict[str, Any]:
    root = getattr(request.app.state, "skills_root", None)
    cfg_path = getattr(request.app.state, "skills_config_path", None)
    ok = skills_config.delete_skill(skill_id, root=root, config_path=cfg_path)
    if not ok:
        raise HTTPException(status_code=404, detail="skill not found")
    return {"ok": True}
