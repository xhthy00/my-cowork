"""TypedDict state for the workforce graph."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def _last_value(left: Any, right: Any) -> Any:
    return right


def merge_subtasks(left: list | None, right: list | None) -> list:
    """Merge subtask lists by id; right fields win."""
    left = list(left or [])
    right = list(right or [])
    if not right:
        return left
    if not left:
        return [dict(t) for t in right]
    index = {str(t.get("id")): dict(t) for t in left if t.get("id")}
    order = [str(t.get("id")) for t in left if t.get("id")]
    for t in right:
        tid = str(t.get("id") or "")
        if not tid:
            continue
        if tid in index:
            index[tid] = {**index[tid], **dict(t)}
        else:
            index[tid] = dict(t)
            order.append(tid)
    return [index[i] for i in order if i in index]


class WorkforceState(TypedDict, total=False):
    """Shared state for coordinator + workers."""

    messages: Annotated[list, operator.add]
    task_id: str
    session_mode: str
    user_text: str
    subtasks: Annotated[list, merge_subtasks]
    assigned_task_id: Annotated[str | None, _last_value]
    round: Annotated[int, operator.add]


# Back-compat alias used by older imports/tests during migration.
SupervisorState = WorkforceState
