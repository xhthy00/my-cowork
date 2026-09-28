"""Single-agent graph: one node running the Act loop."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from app.graphs.routing import wants_document, wants_file_document
from app.graphs.state import SupervisorState
from app.llm.token_counter import count_tokens
from app.runtime.agent_stream import _emit_step_delta
from app.llm.budget_context import context_window_limit
from app.runtime.v2.assemble import assemble_system_messages
from app.runtime.v2.compact import COMPACTION_CAP_TOKENS, compact_session_history
from app.runtime.v2.critic import (
    floor_analysis,
    issues_need_fetch,
    issues_need_search,
)
from app.runtime.v2.loop import inject_forced_fetch, inject_forced_search, run_act_loop
from app.guardrails.office_gate import office_skills_scope
from app.runtime.v2.session import (
    load_compaction, load_thread, save_compaction, save_thread,
    write_compaction_transcript,
)
from app.task_support.todo_context import get_todo_runtime
from app.runtime.v2.synthesize import synthesize_answer

_FLOOR_RETRIES = 3
_SEARCH_GAP_NOTICE = (
    "这次没有拿到检索结果，无法核实当前政策、价格或新闻。"
)


def _search_gap(floor: Any) -> bool:
    if floor is None:
        return False
    return issues_need_search(floor.issues)


async def run_with_floor_retries(
    model: Any,
    tools: list | None,
    messages: list,
    user_text: str,
    *,
    max_retries: int = _FLOOR_RETRIES,
    apply_research: bool | None = None,
    require_findings: bool = False,
    skip_file_gate: bool = False,
    act_max_steps: int | None = None,
) -> list:
    """Act loop, then gate retries with forced search/fetch (LLM critic is optional later)."""
    allow_files = wants_document(user_text)
    tool_names = {
        str(getattr(t, "name", "") or "") for t in (tools or []) if getattr(t, "name", None)
    }
    loop_kwargs: dict[str, Any] = {
        "allow_file_writes": allow_files,
    }
    if act_max_steps is not None:
        loop_kwargs["max_steps"] = act_max_steps
    working = await run_act_loop(
        model, tools or [], messages, **loop_kwargs
    )
    from app.runtime.v2.critic import collect_evidence, evidence_floor_met

    for _ in range(max_retries):
        floor = floor_analysis(
            user_text,
            working,
            apply_research=apply_research,
            require_findings=require_findings,
            skip_file_gate=skip_file_gate,
        )
        if floor is None:
            break
        issues = list(floor.issues or [])
        before = len(working)
        enough = evidence_floor_met(collect_evidence(working, user_text))
        leftover = [
            i
            for i in issues
            if "web_search" not in i and "web_fetch" not in i
        ]
        if enough and not leftover:
            break
        if enough:
            # Already searched/fetched enough — do not inject more queries.
            pass
        elif issues_need_fetch(issues) and not issues_need_search(issues):
            working = await inject_forced_fetch(tools, working)
        elif issues_need_search(issues):
            working = await inject_forced_search(tools, user_text, working)
            if len(working) > before:
                working = await inject_forced_fetch(tools, working)
        if len(working) == before:
            if issues_need_search(issues) and "web_search" not in tool_names:
                break
            if (
                issues_need_fetch(issues)
                and "web_fetch" not in tool_names
                and not issues_need_search(issues)
            ):
                break
            note = (
                "Continue. Missing: "
                + "; ".join(issues)
                + " Call the required tools in this turn. "
                "Do not reply with only an intent or preamble such as「我先搜一下」."
            )
            working = [*working, HumanMessage(content="[Instruction]\n" + note)]
        working = await run_act_loop(
            model,
            tools or [],
            working,
            allow_file_writes=allow_files,
        )
    return working


def compile_single_agent_graph(
    *,
    model: Any,
    tools: list | None,
    synthesize_llm: Any = None,
    recursion_limit: int = 50,
    checkpointer: Any = None,
):
    async def single_agent_node(state: SupervisorState) -> dict:
        user_text = str(state.get("user_text") or "")
        session_id = str(state.get("session_id") or state.get("task_id") or "")
        prefix = assemble_system_messages(
            agent_prompt_name="single_agent",
            assistant_id=str(state.get("assistant_id") or "") or None,
            enabled_skill_ids=list(state.get("enabled_skill_ids") or []),
            knowledge_bases=list(state.get("knowledge_bases") or []) or None,
            session_id=session_id,
            user_text=user_text,
        )
        canonical = [
            m
            for m in (load_thread(session_id) if session_id else [])
            if not _is_system(m)
        ]
        resume_run = bool(get_todo_runtime() and get_todo_runtime().resume_execution)
        prior = canonical
        compaction_state = None
        if not resume_run and session_id:
            previous_state = load_compaction(session_id)
            trigger = min(int(context_window_limit() * 0.8), COMPACTION_CAP_TOKENS)
            history_budget = max(
                1, trigger - count_tokens([*prefix, HumanMessage(content=user_text)]),
            )
            prior, compaction_state = await compact_session_history(
                canonical, previous_state, llm=model, threshold=history_budget,
            )
            if compaction_state is not None:
                boundary = int(compaction_state["boundary_index"])
                if previous_state is None or boundary != previous_state.get("boundary_index"):
                    compaction_state["transcript_path"] = write_compaction_transcript(
                        session_id, canonical, boundary,
                    )
                    save_compaction(session_id, compaction_state)
        if prior and _is_system(prior[0]):
            summary = str(prior[0].content)
            transcript_path = str((compaction_state or {}).get("transcript_path") or "")
            if transcript_path:
                summary += (
                    "\n\n压缩前的逐条原文保存在 " + transcript_path +
                    "。若摘要缺少依据，请用 conversation_read 按序号读取当前会话原文；"
                    "也可读取该文件。不要猜测。"
                )
            prefix = [SystemMessage(content=f"{prefix[0].content}\n\n[较早对话摘要]\n{summary}")]
            prior = prior[1:]
        assembled = [*prefix, *prior]
        runtime = get_todo_runtime()
        if runtime is not None and runtime.source == "schedule" and not resume_run:
            runtime.checkpoint_canonical_prefix = list(canonical)
            runtime.checkpoint_outbound_prefix_len = len(assembled)
        if not (resume_run and prior):
            assembled.append(HumanMessage(content=user_text))
        with office_skills_scope(wants_document(user_text)):
            result = await run_with_floor_retries(
                model, tools or [], assembled, user_text
            )
        floor = floor_analysis(user_text, result)
        final = None
        if _search_gap(floor):
            from app.runtime.context import last_ai_text

            last = last_ai_text(result)
            if len(last.strip()) < 40:
                _emit_step_delta("\n" + _SEARCH_GAP_NOTICE)
                result = [*result, AIMessage(content=_SEARCH_GAP_NOTICE)]
        else:
            from app.runtime.context import (
                is_user_facing_answer,
                last_ai_text,
                looks_like_plan_only,
                looks_like_process_narration,
                looks_like_workspace_dump,
            )
            from app.runtime.v2.synthesize import best_user_facing_text

            last = last_ai_text(result)
            best = best_user_facing_text(result)
            junk_last = looks_like_workspace_dump(last) or looks_like_process_narration(
                last
            )
            thin = looks_like_plan_only(user_text, last) or not (best or last).strip()
            ended_mid_work = _last_ai_called_tools(result) and not is_user_facing_answer(
                last
            )
            salvage = junk_last or thin or ended_mid_work
            need_file = wants_file_document(user_text)
            last_is_delivery = (
                is_user_facing_answer(last)
                and not looks_like_plan_only(user_text, last)
                and not junk_last
            )
            # ChatAgent: reuse a clean earlier reply for Q&A. File tasks that
            # stopped on tool chatter need a user-facing delivery summary.
            if (
                best
                and salvage
                and not need_file
                and not looks_like_plan_only(user_text, best)
            ):
                final = best
            elif need_file and not last_is_delivery:
                final = await synthesize_answer(
                    user_text,
                    result,
                    synthesize_llm or model,
                    rewrite=True,
                )
            elif salvage:
                final = await synthesize_answer(
                    user_text,
                    result,
                    synthesize_llm or model,
                    rewrite=True,
                )
            else:
                final = best or last
            if final and (
                not result or str(getattr(result[-1], "content", "") or "") != final
            ):
                result = [*result, AIMessage(content=final)]
        if session_id:
            if resume_run:
                save_thread(session_id, [m for m in result if not _is_system(m)])
            else:
                # `result` contains the compacted outbound view. Persist only this
                # turn's additions after the full canonical transcript.
                additions = [
                    m for m in result[len(assembled):]
                    if not _is_system(m)
                    and not (str(getattr(m, "type", "")) == "human"
                             and str(getattr(m, "content", "")).startswith("[Instruction]"))
                ]
                save_thread(session_id, [*canonical, *([HumanMessage(content=user_text)]), *additions])
        return {"messages": _delta_after_last_human(result), "round": 0}

    single_agent_node.__name__ = "single_agent_node"
    builder = StateGraph(SupervisorState)
    builder.add_node("single_agent", single_agent_node)
    builder.add_edge(START, "single_agent")
    builder.add_edge("single_agent", END)
    graph = builder.compile(checkpointer=checkpointer)
    graph.recursion_limit = recursion_limit
    return graph


def _last_ai_called_tools(messages: list) -> bool:
    """True when the latest assistant message still has tool_calls (no follow-up)."""
    for msg in reversed(messages or []):
        role = str(getattr(msg, "type", None) or "")
        if role in {"tool", "ToolMessage"}:
            continue
        if role in {"ai", "AIMessage", "assistant"}:
            return bool(getattr(msg, "tool_calls", None))
        if role in {"human", "HumanMessage", "user"}:
            return False
    return False


def _is_human(msg: Any) -> bool:
    role = str(getattr(msg, "type", None) or "")
    if role not in {"human", "HumanMessage", "user"}:
        return False
    content = str(getattr(msg, "content", "") or "")
    return not content.startswith("[Instruction]")


def _is_system(msg: Any) -> bool:
    role = str(getattr(msg, "type", None) or "")
    return role in {"system", "SystemMessage"} or isinstance(msg, SystemMessage)


def _delta_after_last_human(messages: list) -> list:
    """Return AI/tool messages after the latest human turn (skip system)."""
    out: list = []
    for msg in messages:
        if _is_human(msg):
            out = []
            continue
        if _is_system(msg):
            continue
        out.append(msg)
    return out
