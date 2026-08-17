"""Workforce StateGraph: coordinator + specialist workers (Eigent-aligned)."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from app.agents.workers import WORKER_IDS
from app.graphs.routing import (
    apply_retry_or_fail,
    document_tools_succeeded,
    route_after_coordinator,
    wants_document,
    wants_pptx,
)
from app.graphs.state import WorkforceState
from app.runtime.agent_stream import astream_agent_messages

_DOC_NUDGE = (
    "CRITICAL: The user asked for a real document file. In this turn you MUST "
    "write a NEW file to the working directory from [工作空间约束]. "
    "Preferred: load_skill(\"officecli\") then run officecli via bash (create). "
    "Spreadsheets: officecli-xlsx or xlsx_gen. "
    "For 党政公文 / 重新生成公文: load_skill(\"official-document-writing\") "
    "(NOT the generic \"docx\" skill), then officecli, then docx_gongwen_format. "
    "Fallback: docx_gen / pptx_gen / xlsx_gen / pdf_gen. "
    "Do NOT only load_skill. Do NOT invent a path under Documents/AIS or elsewhere. "
    "Never list a file in 交付文件 unless a write tool returned that path. "
    "If the user said 重新生成, write a new file — existing files are not done."
)

_DOC_RETRY_NUDGE = (
    "You finished without writing a document file. Any path in your previous "
    "reply does not count. Call officecli via bash or xlsx_gen/docx_gen/pptx_gen "
    "NOW and write a NEW file under the 最终产出目录. Do not invent a path."
)

_ANSWER_RETRY_NUDGE = (
    "You stopped after planning. Now write the COMPLETE user-facing answer "
    "in Chinese in the message body. Do not only outline. "
    "Unless the user explicitly asked for a file, do not generate docx/xlsx — answer in chat."
)

_PPTX_NUDGE = (
    "CRITICAL: The user asked for PPT/PPTX. You MUST call pptx_gen (not pdf_gen). "
    "Pass slides_json as a JSON STRING. "
    "If pptx_gen returns an error, fix args and call pptx_gen again — never switch to PDF."
)

_PROCESS_PROMPT = """You are executing ONE assigned subtask for a multi-agent workforce.
Focus only on this subtask. Use tools as needed. Prefer shared notes:
list_note / read_note first; after creating files append_note("shared_files", path).

Parent request:
{user_text}

Dependency results:
{deps}

Your subtask ({task_id}):
{content}

When finished, reply with a user-facing Chinese summary of what you delivered
(key findings / file paths). Wrap that summary in <summary>...</summary>.
Do NOT use English meta lines like "Subtask completed" or "Deliverable:".
If you failed, start your final line with FAILED: and a reason.
"""


def _find_subtask(subtasks: list[dict[str, Any]], task_id: str | None) -> dict[str, Any] | None:
    if not task_id:
        return None
    for t in subtasks:
        if str(t.get("id")) == str(task_id):
            return t
    return None


def _dep_block(subtasks: list[dict[str, Any]], task: dict[str, Any]) -> str:
    deps = task.get("dependencies") or []
    if not deps:
        return "(none)"
    by_id = {str(t.get("id")): t for t in subtasks}
    lines: list[str] = []
    for dep in deps:
        other = by_id.get(str(dep))
        if other is None:
            lines.append(f"- {dep}: (missing)")
        else:
            lines.append(
                f"- {dep} [{other.get('assignee')}]: {other.get('result') or '(empty)'}"
            )
    return "\n".join(lines)


def _parse_failed(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if re.search(r"\bFAILED\b", t, re.I):
        return True
    try:
        data = json.loads(t)
        if isinstance(data, dict) and data.get("failed") is True:
            return True
    except json.JSONDecodeError:
        pass
    return False


def _last_ai_text(messages: list[Any]) -> str:
    for msg in reversed(messages):
        role = getattr(msg, "type", None) or getattr(msg, "role", None)
        if str(role) in ("ai", "assistant"):
            return str(getattr(msg, "content", "") or "")
        if isinstance(msg, dict) and str(msg.get("type") or msg.get("role")) in (
            "ai",
            "assistant",
        ):
            return str(msg.get("content") or "")
    return ""


def _make_coordinator_node():
    async def coordinator_node(state: WorkforceState) -> dict:
        # Retry failed tasks under budget, then route_after_coordinator fans out
        # ready waiting tasks. Do not mark running here — that would hide them
        # from ready_subtasks().
        subtasks = apply_retry_or_fail(list(state.get("subtasks") or []))
        return {
            "subtasks": subtasks,
            "assigned_task_id": None,
            "round": 1,
            "messages": [],
        }

    return coordinator_node


def _make_worker_node(worker_agent: Any, name: str):
    async def worker_node(state: WorkforceState) -> dict:
        subtasks = list(state.get("subtasks") or [])
        task_id = state.get("assigned_task_id")
        task = _find_subtask(subtasks, task_id)
        if task is None:
            return {"messages": [], "round": 0}

        user_text = str(state.get("user_text") or "")
        prompt = _PROCESS_PROMPT.format(
            user_text=user_text or "(none)",
            deps=_dep_block(subtasks, task),
            task_id=task.get("id"),
            content=task.get("content"),
        )
        invoke_messages: list[Any] = [HumanMessage(content=prompt)]
        if name == "document_agent" and wants_document(user_text):
            nudge = _PPTX_NUDGE if wants_pptx(user_text) else _DOC_NUDGE
            invoke_messages = [SystemMessage(content=nudge), *invoke_messages]

        result_messages = await astream_agent_messages(worker_agent, invoke_messages)
        messages = list(result_messages)
        summary = _last_ai_text(messages)
        failed = _parse_failed(summary)
        if name == "document_agent" and wants_document(user_text):
            if not document_tools_succeeded(
                {"messages": messages},
                require_pptx=wants_pptx(user_text),
            ):
                failed = True
                if not summary:
                    summary = "FAILED: document tool did not write a file"

        status = "failed" if failed else "completed"
        patch = {
            "id": str(task["id"]),
            "status": status,
            "result": summary[:4000],
            "assignee": name,
            "retries": int(task.get("retries") or 0),
        }
        # Keep full message delta for trace / doc detection across the run.
        return {
            "messages": messages,
            "subtasks": [patch],
            "assigned_task_id": None,
            "round": 0,
        }

    worker_node.__name__ = f"{name}_node"
    return worker_node


def _stub_worker_node(name: str):
    async def worker_node(state: WorkforceState) -> dict:
        raise NotImplementedError(f"Worker {name!r} is not implemented")

    worker_node.__name__ = f"{name}_stub"
    return worker_node


def compile_workforce_graph(
    workers: dict[str, Any],
    recursion_limit: int = 40,
    checkpointer: Any = None,
):
    """Compile coordinator + workers graph (no supervisor routing)."""
    builder = StateGraph(WorkforceState)
    builder.add_node("coordinator", _make_coordinator_node())
    for name in WORKER_IDS:
        if name in workers:
            builder.add_node(name, _make_worker_node(workers[name], name))
        else:
            builder.add_node(name, _stub_worker_node(name))

    builder.add_edge(START, "coordinator")

    route_map: dict[str, Any] = {name: name for name in WORKER_IDS}
    route_map["END"] = END
    builder.add_conditional_edges("coordinator", route_after_coordinator, route_map)
    for name in WORKER_IDS:
        builder.add_edge(name, "coordinator")

    graph = builder.compile(checkpointer=checkpointer)
    graph.recursion_limit = recursion_limit
    return graph


def compile_supervisor_graph(
    supervisor: Any = None,
    workers: dict[str, Any] | None = None,
    recursion_limit: int = 40,
    checkpointer: Any = None,
):
    """Back-compat entry: ignore supervisor agent, build workforce graph."""
    _ = supervisor
    return compile_workforce_graph(
        workers or {}, recursion_limit=recursion_limit, checkpointer=checkpointer
    )
