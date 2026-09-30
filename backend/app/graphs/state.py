"""TypedDict state for the workforce graph."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from app.task_support.state import merge_subtasks


def _last_value(left: Any, right: Any) -> Any:
    return right


class WorkforceState(TypedDict, total=False):
    """Shared state for coordinator + workers."""

    messages: Annotated[list, operator.add]
    task_id: str
    session_id: str
    session_mode: str
    user_text: str
    assistant_id: str
    enabled_skill_ids: list
    knowledge_bases: list
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
