"""Single-agent StateGraph — Eigent-aligned solo ReAct path.

Unlike the workforce graph, this compiles one node that holds the full tool
set and solves the user task directly.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, StateGraph

from app.graphs.routing import (
    _latest_user_text,
    document_tools_succeeded,
    wants_document,
    wants_pptx,
)
from app.graphs.state import SupervisorState
from app.graphs.workforce import (
    _ANSWER_RETRY_NUDGE,
    _DOC_NUDGE,
    _DOC_RETRY_NUDGE,
    _PPTX_NUDGE,
)
from app.runtime.agent_stream import astream_agent_messages
from app.runtime.context import last_ai_text, looks_like_plan_only


def _message_delta(before: list, after: list) -> list:
    if len(after) <= len(before):
        return after[-1:] if after else []
    return after[len(before) :]


def _make_single_agent_node(agent: Any):
    """Wrap a ReAct agent (create_agent) as the sole graph node."""

    async def single_agent_node(state: SupervisorState) -> dict:
        before = list(state.get("messages") or [])
        invoke_messages = before
        user_text = _latest_user_text(state) or str(state.get("user_text") or "")
        from app.runtime.v2.flag import is_v2

        need_doc = wants_document(user_text)
        need_pptx = wants_pptx(user_text)
        if (
            not is_v2()
            and need_doc
            and not document_tools_succeeded(state, require_pptx=need_pptx)
        ):
            nudge = _PPTX_NUDGE if need_pptx else _DOC_NUDGE
            invoke_messages = [*before, SystemMessage(content=nudge)]
        messages = await astream_agent_messages(agent, invoke_messages)
        if not is_v2():
            if need_doc and not document_tools_succeeded(
                {"messages": messages}, require_pptx=need_pptx
            ):
                messages = await astream_agent_messages(
                    agent, [*messages, SystemMessage(content=_DOC_RETRY_NUDGE)]
                )
            elif looks_like_plan_only(user_text, last_ai_text(messages)):
                messages = await astream_agent_messages(
                    agent, [*messages, SystemMessage(content=_ANSWER_RETRY_NUDGE)]
                )
        delta = _message_delta(invoke_messages, messages)
        return {
            "messages": delta,
            "round": 0,
        }

    single_agent_node.__name__ = "single_agent_node"
    return single_agent_node


def compile_single_agent_graph(
    agent: Any,
    recursion_limit: int = 50,
    checkpointer: Any = None,
):
    """Compile START → single_agent → END."""
    builder = StateGraph(SupervisorState)
    builder.add_node("single_agent", _make_single_agent_node(agent))
    builder.add_edge(START, "single_agent")
    builder.add_edge("single_agent", END)
    graph = builder.compile(checkpointer=checkpointer)
    graph.recursion_limit = recursion_limit
    return graph
