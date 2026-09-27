"""Workforce graph: coordinator + Act-loop workers + synthesize."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.agents.factory import load_prompt
from app.agents.workers import WORKER_IDS
from app.graphs.coordinator import coordinate
from app.graphs.routing import MAX_RETRIES, apply_retry_or_fail, ready_subtasks, wants_document
from app.graphs.single_agent import run_with_floor_retries
from app.graphs.state import WorkforceState
from app.runtime.todo_context import automation_checkpoint_scope, get_todo_runtime, todo_agent_scope
from app.runtime.v2.assemble import format_bound_knowledge_block, render_agent_prompt
from app.runtime.v2.critic import (
    analyze_task,
    evidence_digest,
    finalize_worker_result,
    needs_research,
)
from app.runtime.v2.office_gate import office_skills_scope
from app.runtime.v2.compact import compact_session_history
from app.runtime.v2.session import (
    load_compaction, load_thread, save_compaction, write_compaction_transcript,
)
from app.runtime.v2.synthesize import compose_workforce_answer


def _last_text(messages: list[Any]) -> str:
    for msg in reversed(messages):
        role = str(getattr(msg, "type", None) or "")
        if role in {"ai", "AIMessage", "assistant"}:
            return str(getattr(msg, "content", "") or "")
    return ""


def _stub_worker_node(name: str):
    async def worker_node(state: WorkforceState) -> dict:
        raise NotImplementedError(f"Worker {name!r} is not implemented")

    worker_node.__name__ = f"{name}_stub"
    return worker_node


def compile_workforce_graph(
    *,
    workers: dict[str, dict[str, Any]],
    planner_llm: Any = None,
    recursion_limit: int = 40,
    checkpointer: Any = None,
):
    """workers maps id -> {model, tools, prompt_name}."""

    async def earlier_conversation(state: WorkforceState) -> str:
        session_id = str(state.get("session_id") or "")
        if not session_id:
            return ""
        canonical = load_thread(session_id)
        if not canonical:
            return ""
        old_state = load_compaction(session_id)
        visible, new_state = await compact_session_history(
            canonical, old_state, llm=planner_llm, threshold=12_000,
        )
        if new_state is not None and (
            old_state is None or new_state["boundary_index"] != old_state.get("boundary_index")
        ):
            new_state["transcript_path"] = write_compaction_transcript(
                session_id, canonical, int(new_state["boundary_index"]),
            )
            save_compaction(session_id, new_state)
        lines = ["[同一会话的较早对话；当前用户消息仍是本轮目标]"]
        for message in visible:
            role = str(getattr(message, "type", "") or "")
            label = "摘要" if role == "system" else "用户" if role == "human" else "助手"
            lines.append(f"{label}：{str(getattr(message, 'content', '') or '')}")
        transcript = str((new_state or {}).get("transcript_path") or "")
        if transcript:
            lines.append(
                f"摘要缺少细节时，用 conversation_read 回查当前会话；原文文件：{transcript}"
            )
        return "\n".join(lines)

    async def coordinator_node(state: WorkforceState) -> dict:
        subtasks = apply_retry_or_fail(list(state.get("subtasks") or []))
        user_text = str(state.get("user_text") or "")
        bound = format_bound_knowledge_block(state.get("knowledge_bases"))
        earlier = await earlier_conversation(state)
        coord_text = "\n\n".join(part for part in (bound, earlier, user_text) if part)
        decision = await coordinate(coord_text, subtasks, planner_llm)
        action = str(decision.get("action") or "finish")
        if action == "rework":
            by_id = {str(t.get("id")): t for t in subtasks}
            for item in decision.get("rework") or []:
                if not isinstance(item, dict):
                    continue
                tid = str(item.get("id") or "")
                task = by_id.get(tid)
                if task is None:
                    continue
                if str(task.get("status") or "") != "failed":
                    continue
                retries = int(task.get("retries") or 0)
                if retries >= MAX_RETRIES:
                    continue
                task["status"] = "waiting"
                task["result"] = ""
                task["retries"] = retries + 1
                if item.get("brief"):
                    task["content"] = str(item["brief"])
        briefs = {
            str(a.get("id")): str(a.get("brief") or "")
            for a in (decision.get("assignments") or [])
            if isinstance(a, dict) and a.get("id")
        }
        rnd = int(state.get("round") or 0) + 1
        return {
            "subtasks": subtasks,
            "coord_action": action,
            "coord_briefs": briefs,
            "assigned_task_id": None,
            "round": rnd,
            "messages": [],
        }

    def route_after(state: dict[str, Any]) -> Any:
        action = str(state.get("coord_action") or "")
        subtasks = list(state.get("subtasks") or [])
        ready = ready_subtasks(subtasks)
        if action == "finish" and not ready:
            return "synthesize"
        round_n = int(state.get("round") or 0)
        if round_n >= 16 and not ready:
            return "synthesize"
        briefs = dict(state.get("coord_briefs") or {})
        if action == "rework":
            ready = ready_subtasks(subtasks)
        if not ready:
            return "synthesize"
        sends: list[Send] = []
        for t in ready:
            assignee = str(t.get("assignee") or "")
            if assignee not in workers:
                if workers:
                    assignee = (
                        "browser_agent"
                        if "browser_agent" in workers
                        else next(iter(workers))
                    )
                elif assignee not in WORKER_IDS:
                    assignee = "developer_agent"
            sends.append(
                Send(
                    assignee,
                    {
                        **state,
                        "subtasks": subtasks,
                        "assigned_task_id": str(t["id"]),
                        "worker_brief": briefs.get(str(t["id"])) or str(t.get("content") or ""),
                    },
                )
            )
        return sends if sends else "synthesize"

    def _make_worker(name: str):
        spec = workers[name]
        model = spec["model"]
        tools = spec.get("tools") or []
        prompt_name = spec.get("prompt_name") or name.replace("_agent", "")

        async def worker_node(state: WorkforceState) -> dict:
            subtasks = list(state.get("subtasks") or [])
            task_id = state.get("assigned_task_id")
            task = next((t for t in subtasks if str(t.get("id")) == str(task_id)), None)
            if task is None:
                return {"messages": []}
            user_text = str(state.get("user_text") or "")
            brief = str(state.get("worker_brief") or task.get("content") or "")
            deps = task.get("dependencies") or []
            by_id = {str(t.get("id")): t for t in subtasks}
            dep_lines = []
            for dep in deps:
                other = by_id.get(str(dep))
                if other is None:
                    dep_lines.append(f"- {dep}: (missing)")
                else:
                    dep_lines.append(
                        f"- {dep} [{other.get('assignee')}]: {other.get('result') or '(empty)'}"
                    )
            prompt = load_prompt(
                "worker_brief",
                user_text=user_text or "(none)",
                deps="\n".join(dep_lines) or "(none)",
                task_id=str(task.get("id")),
                content=brief,
            )
            system = render_agent_prompt(prompt_name)
            bound = format_bound_knowledge_block(state.get("knowledge_bases"))
            if bound:
                system = f"{system.rstrip()}\n\n{bound}\n"
            from app.runtime.memory_context import get_long_term_runtime
            from app.memory.scoped import project_memory_key

            memory_store = get_long_term_runtime()
            runtime = get_todo_runtime()
            if memory_store is not None and hasattr(memory_store, "prompt_block"):
                memory_key = project_memory_key(
                    runtime.memory_root if runtime else None,
                    runtime.project_id if runtime else None,
                )
                memory_block = memory_store.prompt_block(
                    workspace=memory_key, session_id=str(state.get("session_id") or "") or None,
                )
                if memory_block:
                    system = f"{system.rstrip()}\n\n{memory_block}\n"
                settings = getattr(memory_store, "memory_settings", None)
                if settings is not None and not settings.enabled:
                    system += "\n记忆写入已关闭。已有记忆仍可读，不要保存新记忆。\n"
                else:
                    system += ("\n长期偏好与纠正用 remember(scope='global')；"
                               "项目中无法从文件重建的事实用 scope='workspace'。"
                               "已有条目用 memory_update；敏感信息先征得用户同意。\n")
            earlier = await earlier_conversation(state)
            if earlier:
                system += f"\n{earlier}\n"
            invoke = [SystemMessage(content=system), HumanMessage(content=prompt)]
            checkpoint_key = f"{state.get('session_id')}:worker:{task_id}"
            if runtime is not None and runtime.resume_execution:
                prior = load_thread(checkpoint_key)
                if prior:
                    invoke = [SystemMessage(content=system), *prior]
            # Gate office on the original user ask, not a planner brief that
            # invented「再生成 Word」after the user only wanted Markdown.
            format_text = user_text or brief
            with todo_agent_scope(name):
                with automation_checkpoint_scope(checkpoint_key):
                    with office_skills_scope(wants_document(format_text)):
                        result_messages = await run_with_floor_retries(
                            model,
                            tools,
                            invoke,
                            format_text,
                            max_retries=1,
                            act_max_steps=18,
                            skip_file_gate=name == "browser_agent",
                            apply_research=(
                                name == "browser_agent"
                                and needs_research(f"{user_text} {brief}")
                            ),
                            require_findings=(
                                name == "browser_agent"
                                and needs_research(f"{user_text} {brief}")
                            ),
                        )
            summary = _last_text(result_messages)
            digest = evidence_digest(result_messages)
            if digest:
                summary = (summary or "").rstrip() + "\n\n" + digest
            failed = (
                not summary.strip() or summary.strip().upper().startswith("FAILED")
            )
            analysis = await analyze_task(
                brief,
                summary,
                for_failure=failed,
                error_message=summary if failed else None,
                llm=planner_llm,
                failure_count=int(task.get("retries") or 0),
                messages=result_messages,
                user_text=user_text,
                task_id=str(task.get("id") or ""),
                assigned_worker=name,
            )
            patch = finalize_worker_result(
                task=task,
                summary=summary,
                analysis=analysis,
                max_retries=MAX_RETRIES,
            )
            patch["assignee"] = name
            return {
                "messages": result_messages,
                "subtasks": [patch],
                "assigned_task_id": None,
            }

        worker_node.__name__ = f"{name}_node"
        return worker_node

    async def synthesize_node(state: WorkforceState) -> dict:
        user_text = str(state.get("user_text") or "")
        with todo_agent_scope("synthesize"):
            text = await compose_workforce_answer(
                user_text,
                subtasks=list(state.get("subtasks") or []),
                messages=list(state.get("messages") or []),
                llm=planner_llm,
            )
        return {"messages": [AIMessage(content=text)], "coord_action": "done"}

    builder = StateGraph(WorkforceState)
    builder.add_node("coordinator", coordinator_node)
    builder.add_node("synthesize", synthesize_node)
    for name in WORKER_IDS:
        if name in workers:
            builder.add_node(name, _make_worker(name))
        else:
            builder.add_node(name, _stub_worker_node(name))

    builder.add_edge(START, "coordinator")
    route_map: dict[str, Any] = {name: name for name in WORKER_IDS}
    route_map["synthesize"] = "synthesize"
    route_map["END"] = END
    builder.add_conditional_edges("coordinator", route_after, route_map)
    for name in WORKER_IDS:
        builder.add_edge(name, "coordinator")
    builder.add_edge("synthesize", END)
    graph = builder.compile(checkpointer=checkpointer)
    graph.recursion_limit = recursion_limit
    return graph
