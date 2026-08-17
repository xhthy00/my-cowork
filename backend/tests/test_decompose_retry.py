"""Decompose + retry helpers."""

from app.graphs.routing import MAX_RETRIES, apply_retry_or_fail
from app.runtime.decompose import fallback_subtasks, normalize_subtasks, parse_subtasks_json


def test_fallback_assigns_document_for_pptx():
    tasks = fallback_subtasks("生成一份 PPT 攻略")
    assert len(tasks) == 1
    assert tasks[0]["assignee"] == "document_agent"


def test_parse_subtasks_json():
    raw = """
    [
      {"id":"task_1","content":"检索","assignee":"browser_agent","dependencies":[]},
      {"id":"task_2","content":"写PPT","assignee":"document_agent","dependencies":["task_1"]}
    ]
    """
    tasks = parse_subtasks_json(raw)
    assert len(tasks) == 2
    assert tasks[1]["dependencies"] == ["task_1"]


def test_normalize_maps_legacy_assignee():
    tasks = normalize_subtasks(
        [{"id": "a", "content": "x", "assignee": "doc_worker", "dependencies": []}]
    )
    assert tasks[0]["assignee"] == "document_agent"


def test_retry_resets_failed_under_budget():
    subtasks = [
        {
            "id": "a",
            "content": "x",
            "assignee": "browser_agent",
            "dependencies": [],
            "status": "failed",
            "result": "boom",
            "retries": 0,
        }
    ]
    out = apply_retry_or_fail(subtasks)
    assert out[0]["status"] == "waiting"
    assert out[0]["retries"] == 1

    subtasks[0]["retries"] = MAX_RETRIES
    subtasks[0]["status"] = "failed"
    out2 = apply_retry_or_fail(subtasks)
    assert out2[0]["status"] == "failed"
