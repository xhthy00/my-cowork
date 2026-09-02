"""IMA knowledge-base status / connection test."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.tools.builtin.ima.client import ImaClient, ImaCredentialError, ImaError
from app.tools.builtin.ima.credentials import MISSING_CREDENTIALS_MSG, configured
from app.tools.builtin.ima.wiki import list_visible_knowledge_bases

router = APIRouter()


@router.get("/api/ima/status")
async def ima_status() -> dict[str, Any]:
    return {"configured": configured()}


@router.get("/api/ima/knowledge-bases")
async def ima_knowledge_bases() -> dict[str, Any]:
    """List wiki libraries for the composer picker. Always 200 so the UI can
    distinguish missing keys vs empty libraries vs upstream errors."""
    if not configured():
        return {"configured": False, "items": [], "empty": True, "hint": ""}
    try:
        data = await list_visible_knowledge_bases(
            ImaClient(), query="", cursor="", limit=20
        )
    except ImaCredentialError as exc:
        return {"configured": False, "items": [], "empty": True, "hint": str(exc)}
    except ImaError as exc:
        return {"configured": True, "items": [], "empty": True, "hint": str(exc)}
    items = data.get("items") if isinstance(data.get("items"), list) else []
    rows = [
        {
            "id": str(item.get("id") or "").strip(),
            "name": str(item.get("name") or "").strip(),
            "source": "ima",
        }
        for item in items
        if isinstance(item, dict)
        and (str(item.get("id") or "").strip() or str(item.get("name") or "").strip())
    ]
    return {
        "configured": True,
        "items": rows,
        "empty": len(rows) == 0,
        "hint": data.get("hint") or "",
    }


@router.post("/api/ima/test")
async def ima_test() -> dict[str, Any]:
    if not configured():
        raise HTTPException(status_code=400, detail=MISSING_CREDENTIALS_MSG)
    try:
        data = await list_visible_knowledge_bases(ImaClient(), query="", cursor="", limit=20)
    except ImaCredentialError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ImaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    items = data.get("items") if isinstance(data.get("items"), list) else []
    names = [
        str(item.get("name") or "").strip()
        for item in items
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    return {
        "ok": True,
        "configured": True,
        "sample_count": len(items),
        "names": names[:8],
        "empty": len(items) == 0,
        "hint": data.get("hint") or "",
    }
