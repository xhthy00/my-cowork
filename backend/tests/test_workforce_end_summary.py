from app.runtime.output_text import is_process_meta, resolve_workforce_end_summary


def test_process_meta_subtask_completed():
    assert is_process_meta(
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


def test_resolve_does_not_concatenate_every_worker():
    subs = [
        {"id": "task_1", "result": "<summary>调研笔记 A</summary>"},
        {"id": "task_2", "result": "<summary>整体购房建议</summary>"},
    ]
    assert resolve_workforce_end_summary(subs) == "整体购房建议"
    assert "调研笔记 A" not in resolve_workforce_end_summary(subs)


    from app.runtime.context import strip_think_blocks

    assert strip_think_blocks("内部推理一大段\n</think>\n扬州已取消限购。") == (
        "扬州已取消限购。"
    )
    cleaned = strip_think_blocks("<think>plan</think>\n扬州已取消限购。")
    assert "扬州已取消限购" in cleaned
    assert "plan" not in cleaned
