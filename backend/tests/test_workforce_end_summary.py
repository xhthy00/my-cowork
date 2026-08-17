from app.runtime.graph_runner import (
    _is_process_meta,
    resolve_workforce_end_summary,
)


def test_process_meta_subtask_completed():
    assert _is_process_meta(
        "Subtask completed. Deliverable:\n- /tmp/a.md (12 chars)"
    )


def test_resolve_prefers_summary_tag():
    subs = [
        {
            "id": "task_1",
            "result": "<think>x</think>\nSubtask completed.\n<summary>## 结论\n已完成</summary>",
        }
    ]
    assert resolve_workforce_end_summary(subs) == "## 结论\n已完成"


def test_resolve_skips_english_meta_only():
    subs = [{"id": "task_1", "result": "All tasks completed.\nAll done."}]
    assert resolve_workforce_end_summary(subs) == ""
