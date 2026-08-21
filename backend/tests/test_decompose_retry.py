"""Decompose + retry helpers."""

from app.graphs.routing import MAX_RETRIES, apply_retry_or_fail
from app.runtime.decompose import (
    align_subtasks_to_user_format,
    fallback_subtasks,
    normalize_subtasks,
    parse_subtasks_json,
)


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


def test_align_md_only_rewrites_invented_word_brief():
    tasks = [
        {
            "id": "task_1",
            "content": "创建 Word 文档并搭建标题与元信息",
            "assignee": "document_agent",
            "dependencies": [],
            "status": "waiting",
            "result": "",
            "retries": 0,
        }
    ]
    out = align_subtasks_to_user_format("帮我将内容转成md文件", tasks)
    assert "Word" not in out[0]["content"]
    assert ".md" in out[0]["content"].lower() or "Markdown" in out[0]["content"]

    keep = align_subtasks_to_user_format("帮我生成一份 Word 报告", tasks)
    assert "Word" in keep[0]["content"]
