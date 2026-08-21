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
    session_id: str
    session_mode: str
    user_text: str
    assistant_id: str
    enabled_skill_ids: list
    subtasks: Annotated[list, merge_subtasks]
    assigned_task_id: Annotated[str | None, _last_value]
    worker_brief: Annotated[str, _last_value]
    coord_action: Annotated[str, _last_value]
    coord_briefs: Annotated[dict, _last_value]
    # last_value so a new turn (round=0) does not inherit the previous
    # run's accumulated count (operator.add + shared thread_id ended instantly).
    round: Annotated[int, _last_value]


# Back-compat alias used by older imports/tests during migration.
SupervisorState = WorkforceState
