"""SSE chat endpoint for the desktop agent."""

import json
import uuid
from typing import Any, AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.orchestrator.task_manager import TaskRequest
from app.runtime.decompose import normalize_subtasks

router = APIRouter()

# Active streaming task ids — used by /api/chat/stop
_active_tasks: dict[str, bool] = {}


class ChatHistoryTurn(BaseModel):
    """One prior chat turn from the desktop session."""

    role: str
    content: str


class BoundKnowledgeBase(BaseModel):
    """Composer-bound knowledge library (IMA today)."""

    id: str = ""
    name: str = ""
    source: str = "ima"


class ChatRequest(BaseModel):
    """Request body for POST /api/chat."""

    text: str = Field(..., min_length=1)
    task_id: str | None = None
    session_mode: str = "workforce"
    memory_enabled: bool = True
    enabled_mcp: list[str] | None = None
    history: list[ChatHistoryTurn] | None = None
    space_id: str | None = None
    project_id: str | None = None
    space_root_path: str | None = None
    workdir_mode: str | None = None
    assistant_id: str | None = None
    enabled_skill_ids: list[str] | None = None
    knowledge_bases: list[BoundKnowledgeBase] | None = None
    session_id: str | None = None


class WorkforceStartBody(BaseModel):
    """Confirm / edit workforce subtasks and resume execution."""

    task_id: str
    subtasks: list[dict[str, Any]] = Field(default_factory=list)


class StopBody(BaseModel):
    """Optional body for stop endpoints."""

    task_id: str | None = None


async def _event_stream(
    task_manager: Any, req: ChatRequest
) -> AsyncIterator[str]:
    """Yield SSE formatted lines from the task manager event stream."""
    task_req = TaskRequest(
        text=req.text,
        task_id=req.task_id or str(uuid.uuid4()),
        session_mode=req.session_mode,
        memory_enabled=req.memory_enabled,
        enabled_mcp=req.enabled_mcp,
        history=[t.model_dump() for t in (req.history or [])] or None,
        space_id=req.space_id,
        project_id=req.project_id,
        space_root_path=req.space_root_path,
        workdir_mode=req.workdir_mode,
        assistant_id=req.assistant_id,
        enabled_skill_ids=req.enabled_skill_ids,
        knowledge_bases=[row.model_dump() for row in (req.knowledge_bases or [])] or None,
        session_id=req.session_id or req.project_id,
    )
    task_id = task_req.task_id or "stream"
    _active_tasks[task_id] = True
    try:
        async for event in task_manager.handle(task_req):
            if not _active_tasks.get(task_id, True):
                # Best-effort cancel underlying graph if stop flipped the flag.
                if hasattr(task_manager, "cancel"):
                    task_manager.cancel(task_id)
                yield f"data: {json.dumps({'type': 'graph.end', 'status': 'cancelled', 'task_id': task_id}, ensure_ascii=False)}\n\n"
                break
            tid = str(event.get("task_id") or task_id)
            _active_tasks[tid] = _active_tasks.get(task_id, True)
            yield f"data: {json.dumps(event, ensure_ascii=False, separators=(',', ':'))}\n\n"
            if event.get("type") == "graph.end":
                break
    finally:
        _active_tasks.pop(task_id, None)


@router.post("/api/chat")
async def chat(request: Request, body: ChatRequest) -> StreamingResponse:
    """Submit a chat request and stream trace events via SSE."""
    task_manager = request.app.state.task_manager
    return StreamingResponse(
        _event_stream(task_manager, body),
        media_type="text/event-stream",
    )


@router.post("/api/workforce/start")
async def workforce_start(request: Request, body: WorkforceStartBody) -> dict[str, Any]:
    """Resolve a pending plan confirmation with (optional) edited subtasks."""
    hub = request.app.state.confirm_hub
    subtasks = normalize_subtasks(body.subtasks)
    hub.resolve_plan(body.task_id, subtasks)
    return {"ok": True, "task_id": body.task_id, "count": len(subtasks)}


@router.post("/api/chat/stop")
async def stop_chat(request: Request, body: StopBody | None = None) -> dict[str, Any]:
    """Cancel active chat task(s) via TaskManager.cancel."""
    task_manager = request.app.state.task_manager
    task_id = body.task_id if body else None
    cancelled = 0
    if task_id:
        _active_tasks[task_id] = False
        if hasattr(task_manager, "cancel") and task_manager.cancel(task_id):
            cancelled = 1
    else:
        for key in list(_active_tasks.keys()):
            _active_tasks[key] = False
        if hasattr(task_manager, "cancel_all"):
            cancelled = task_manager.cancel_all()
        elif hasattr(task_manager, "cancel"):
            for key in list(_active_tasks.keys()):
                if task_manager.cancel(key):
                    cancelled += 1
    return {"ok": True, "cancelled": cancelled}


@router.post("/api/task/{task_id}/cancel")
async def cancel_task(task_id: str, request: Request) -> dict[str, Any]:
    """Cancel a specific running task."""
    task_manager = request.app.state.task_manager
    _active_tasks[task_id] = False
    ok = False
    if hasattr(task_manager, "cancel"):
        ok = bool(task_manager.cancel(task_id))
    return {"ok": ok, "task_id": task_id}
