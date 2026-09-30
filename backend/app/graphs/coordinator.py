"""LLM workforce coordinator (v2)."""

from __future__ import annotations

import json
import re
from typing import Any

from app.agents.factory import load_prompt
from app.graphs.routing import ready_subtasks
from app.runtime.notes_context import notes_excerpt

_JSON_RE = re.compile(r"\{[\s\S]*\}")


def _parse(raw: str) -> dict[str, Any]:
    m = _JSON_RE.search(raw or "")
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


async def coordinate(
    user_text: str,
    subtasks: list[dict[str, Any]],
    llm: Any | None,
) -> dict[str, Any]:
    """Return {action, assignments, rework, finish_reason}."""
    ready = ready_subtasks(subtasks)
    all_done = bool(subtasks) and all(
        str(t.get("status")) in {"completed", "failed"} for t in subtasks
    )
    failed = [t for t in subtasks if str(t.get("status")) == "failed"]
    # Dispatch / finish are deterministic. Calling the coordinator LLM here
    # used to re-open completed research ("need more sources") for another
    # 40-step search loop.
    if llm is None or all_done or (ready and not failed):
        if all_done:
            return {
                "action": "finish",
                "assignments": [],
                "rework": [],
                "finish_reason": "all completed" if not failed else "terminal",
            }
        return {
            "action": "dispatch",
            "assignments": [
                {"id": str(t.get("id")), "brief": str(t.get("content") or "")}
                for t in ready
            ],
            "rework": [],
            "finish_reason": "",
        }

    prompt = load_prompt(
        "coordinator",
        user_text=user_text or "",
        subtasks=json.dumps(subtasks, ensure_ascii=False)[:12_000],
        notes=notes_excerpt()[:4000],
    )
    try:
        msg = await llm.ainvoke(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Return the JSON coordination decision now."},
            ]
        )
        data = _parse(str(getattr(msg, "content", None) or msg))
    except Exception:
        data = {}
    action = str(data.get("action") or "").strip().lower()
    if action not in {"dispatch", "rework", "finish"}:
        action = "finish" if all_done and not failed else "dispatch"
    assignments = data.get("assignments") if isinstance(data.get("assignments"), list) else []
    rework = data.get("rework") if isinstance(data.get("rework"), list) else []
    failed_ids = {str(t.get("id")) for t in failed}
    rework = [
        item
        for item in rework
        if isinstance(item, dict) and str(item.get("id") or "") in failed_ids
    ]
    if action == "rework" and not rework:
        action = "dispatch" if ready else "finish"
    if action == "dispatch" and not assignments:
        assignments = [
            {"id": str(t.get("id")), "brief": str(t.get("content") or "")} for t in ready
        ]
        assignments = [
            {"id": str(t.get("id")), "brief": str(t.get("content") or "")} for t in ready
        ]
    return {
        "action": action,
        "assignments": assignments,
        "rework": rework,
        "finish_reason": str(data.get("finish_reason") or ""),
    }
