"""Human confirmation resolution endpoint."""

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class ConfirmBody(BaseModel):
    """Request body for POST /api/tool/confirm/{call_id}."""

    ok: bool


@router.post("/api/tool/confirm/{call_id}")
async def confirm(call_id: str, body: ConfirmBody, request: Request) -> dict[str, Any]:
    """Resolve a pending tool confirmation request."""
    hub = request.app.state.confirm_hub
    resolved = hub.resolve(call_id, body.ok)
    audit = getattr(request.app.state, "audit_store", None)
    if audit is not None:
        try:
            audit.log(
                kind="confirm_resolve_http",
                call_id=call_id,
                ok=body.ok,
                detail={"resolved": resolved},
            )
        except Exception:
            pass
    return {"ok": True, "resolved": resolved}
