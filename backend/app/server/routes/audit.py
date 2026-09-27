"""Read-only audit trail for the local desktop."""

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/api/audit")
def audit(request: Request, task_id: str = "", session_id: str = "", limit: int = 100) -> dict[str, Any]:
    store = getattr(request.app.state, "audit_store", None)
    return {"events": store.list_recent(task_id=task_id, session_id=session_id, limit=limit) if store else []}
