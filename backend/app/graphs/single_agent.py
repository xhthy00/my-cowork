"""Single-agent graph: one node running the Act loop."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from app.graphs.routing import wants_document
from app.graphs.state import SupervisorState
from app.runtime.agent_stream import _emit_step_delta
from app.runtime.v2.assemble import assemble_system_messages
from app.runtime.v2.compact import compact_messages
from app.runtime.v2.critic import (
    floor_analysis,
    issues_need_fetch,
    issues_need_search,
)
from app.runtime.v2.loop import inject_forced_fetch, inject_forced_search, run_act_loop
from app.runtime.v2.office_gate import office_skills_scope
from app.runtime.v2.session import load_thread, save_thread
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
            user_text=user_text,
        )
        prior = [
            m
            for m in (load_thread(session_id) if session_id else [])
            if not _is_system(m)
        ]
        prior = await compact_messages(prior, llm=model)
        assembled = [*prefix, *prior, HumanMessage(content=user_text)]
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
            salvage = junk_last or thin
            # ChatAgent: the last user-facing reply is the answer. Synthesize
            # only salvages dump / empty / plan, or office-file delivery.
            if (
                best
                and salvage
                and not wants_document(user_text)
                and not looks_like_plan_only(user_text, best)
            ):
                final = best
            elif wants_document(user_text) or salvage:
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
            save_thread(session_id, [m for m in result if not _is_system(m)])
        return {"messages": _delta_after_last_human(result), "round": 0}

    single_agent_node.__name__ = "single_agent_node"
    builder = StateGraph(SupervisorState)
    builder.add_node("single_agent", single_agent_node)
    builder.add_edge(START, "single_agent")
    builder.add_edge("single_agent", END)
    graph = builder.compile(checkpointer=checkpointer)
    graph.recursion_limit = recursion_limit
    return graph


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
