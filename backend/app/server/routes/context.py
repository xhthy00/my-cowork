"""Read and compact a session's model view without changing its transcript."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.llm.gateway import create_configured_model
from app.llm.model_config import model_scope
from app.llm.token_counter import count_tokens
from app.runtime.v2.compact import compact_session_history, session_view, effective_compaction_state
from app.runtime.v2.session import get_session_store

router = APIRouter()


class CompactRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=200)
    model_profile_id: str | None = None
    focus: str = Field(default="", max_length=4000)
    reasoning: dict | None = None


def model_config(request: Request, profile_id: str | None):
    registry = request.app.state.task_manager.model_registry
    try:
        if registry is None:
            raise ValueError()
        return registry.resolve(profile_id)
    except ValueError:
        raise HTTPException(400, "请先选择有效模型") from None


@router.get("/api/context")
async def context_usage(request: Request, session_id: str, model_profile_id: str | None = None):
    config = model_config(request, model_profile_id)
    store = get_session_store()
    canonical = store.load(session_id)
    state = store.load_compaction(session_id)
    with model_scope(config):
        view = session_view(canonical, state)
        compacted = bool(effective_compaction_state(canonical, state))
    return {"tokens": count_tokens(view), "limit": config.context_window,
            "input_budget": config.input_budget, "trigger": config.compression_trigger, "compacted": compacted}


@router.post("/api/context/compact")
async def compact(request: Request, body: CompactRequest):
    manager = request.app.state.task_manager
    with manager.admission.work("上下文压缩"):
        sid = body.session_id
        if manager.session_busy(sid) or sid in manager.compacting_sessions:
            raise HTTPException(409, "会话忙碌中，请等待任务结束后压缩")
        config = model_config(request, body.model_profile_id)
        if body.reasoning is not None:
            try:
                config = config.with_reasoning(body.reasoning)
            except ValueError as error:
                raise HTTPException(400, str(error)) from None
        manager.compacting_sessions.add(sid)
        try:
            store = get_session_store()
            original = store.load(sid)
            old = store.load_compaction(sid)
            with model_scope(config):
                before = count_tokens(session_view(original, old))
                view, updated = await compact_session_history(original, old, llm=create_configured_model(config), force=True, focus=body.focus)
            if await request.is_disconnected():
                raise HTTPException(409, "压缩已取消，原上下文已保留")
            # No await between comparison and persistence: concurrent HTTP edits cannot interleave.
            if store.load(sid) != original or store.load_compaction(sid) != old:
                raise HTTPException(409, "会话已变化，压缩结果未应用")
            if updated is None:
                raise ValueError("没有可压缩的较早对话")
            updated["transcript_path"] = store.write_compaction_transcript(sid, original, updated["boundary_index"])
            store.save_compaction(sid, updated)
            return {"tokens": count_tokens(view), "before_tokens": before, "limit": config.context_window, "compacted": True}
        except ValueError as error:
            raise HTTPException(400, str(error)) from None
        finally:
            manager.compacting_sessions.discard(sid)
