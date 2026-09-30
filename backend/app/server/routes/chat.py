"""SSE chat endpoint for the desktop agent."""

import json
import uuid
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException, Request
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


class TaskBudgetBody(BaseModel):
    max_tokens: int | None = Field(..., gt=0, le=9_007_199_254_740_991, strict=True)


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
    model_profile_id: str | None = None
    reasoning: dict | None = None
    task_budget: TaskBudgetBody | None = None


class WorkforceStartBody(BaseModel):
    """Confirm / edit workforce subtasks and resume execution."""

    task_id: str
    subtasks: list[dict[str, Any]] = Field(default_factory=list)


class StopBody(BaseModel):
    """Optional body for stop endpoints."""

    task_id: str | None = None


class HumanReplyBody(BaseModel):
    question_id: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)


def _task_request(req: ChatRequest) -> TaskRequest:
    return TaskRequest(
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
        model_profile_id=req.model_profile_id,
        reasoning=req.reasoning,
        task_budget=req.task_budget.model_dump() if req.task_budget is not None else None,
    )
async def _event_stream(task_manager: Any, req: ChatRequest, task_req: TaskRequest | None = None) -> AsyncIterator[str]:
    task_req = task_req or _task_request(req)
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
    task_req = _task_request(body)
    try:
        if hasattr(task_manager, "prepare_task"):
            task_manager.prepare_task(task_req)
    except ValueError as error:
        raise HTTPException(400, str(error)) from None
    return StreamingResponse(
        _event_stream(task_manager, body, task_req),
        media_type="text/event-stream",
    )


@router.get("/api/budget/settings")
async def budget_settings(request: Request) -> dict:
    return request.app.state.task_manager.budget_settings()


@router.get("/api/budget/paused")
async def paused_budgets(request: Request) -> dict:
    return {"tasks": request.app.state.task_manager.paused_budgets()}


@router.put("/api/budget/settings")
async def save_budget_settings(request: Request, body: TaskBudgetBody) -> dict:
    settings = body.model_dump()
    request.app.state.task_manager.set_budget_settings(settings)
    return settings


@router.post("/api/chat/{task_id}/budget/resume")
async def resume_budget(task_id: str, request: Request, body: TaskBudgetBody) -> dict:
    try:
        request.app.state.task_manager.resume_budget(task_id, body.max_tokens)
    except (ValueError, KeyError) as exc:
        raise HTTPException(409, str(exc)) from None
    return {"ok": True}


@router.post("/api/workforce/start")
async def workforce_start(request: Request, body: WorkforceStartBody) -> dict[str, Any]:
    """Resolve a pending plan confirmation with (optional) edited subtasks."""
    hub = request.app.state.confirm_hub
    subtasks = normalize_subtasks(body.subtasks)
    hub.resolve_plan(body.task_id, subtasks)
    return {"ok": True, "task_id": body.task_id, "count": len(subtasks)}


@router.get("/api/chat/{task_id}/pending-questions")
async def pending_human_questions(task_id: str, request: Request) -> dict[str, Any]:
    hub = getattr(request.app.state, "human_input_hub", None)
    return {"questions": hub.pending(task_id) if hub is not None else []}


@router.get("/api/chat/{task_id}/question-history")
async def human_question_history(task_id: str, request: Request) -> dict[str, Any]:
    hub = getattr(request.app.state, "human_input_hub", None)
    return {"questions": hub.history(task_id) if hub is not None else []}


@router.post("/api/chat/{task_id}/human-reply")
async def human_reply(task_id: str, body: HumanReplyBody, request: Request) -> dict[str, Any]:
    hub = getattr(request.app.state, "human_input_hub", None)
    if hub is None or not hub.reply(task_id, body.question_id, body.answer):
        raise HTTPException(status_code=409, detail="Question is no longer waiting for a reply")
    return {"ok": True, "question_id": body.question_id}


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
