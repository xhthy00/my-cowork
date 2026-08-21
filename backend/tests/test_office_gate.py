from app.runtime.todo_context import (
    TodoRuntime,
    reset_todo_runtime,
    set_todo_runtime,
)
from app.runtime.v2.office_gate import (
    is_office_skill,
    is_office_write_command,
    office_skills_allowed,
    office_skills_scope,
    office_writes_blocked,
)
from app.tools.builtin.todo import todo_write


def test_is_office_skill_names():
    assert is_office_skill("officecli-docx")
    assert is_office_skill("official-document-writing")
    assert is_office_skill("pptx")
    assert not is_office_skill("demo")
    assert not is_office_skill("pdf")


def test_office_skills_scope_resets():
    assert office_skills_allowed() is True
    with office_skills_scope(False):
        assert office_skills_allowed() is False
    assert office_skills_allowed() is True


def test_todo_write_rejects_office_when_gated():
    class _Bus:
        def emit(self, _event):
            pass

    runtime = TodoRuntime(task_id="t1", bus=_Bus())
    token = set_todo_runtime(runtime)
    try:
        with office_skills_scope(False):
            msg = todo_write(
                [
                    {
                        "content": "调用 officecli 生成 .docx",
                        "active_form": "正在生成文档",
                        "status": "in_progress",
                    }
                ]
            )
        assert msg.startswith("[ERROR]")
        assert runtime.todos == []
    finally:
        reset_todo_runtime(token)


def test_office_writes_blocked_on_markdown_only_todo():
    class _Bus:
        def emit(self, _event):
            pass

    runtime = TodoRuntime(
        task_id="t1",
        bus=_Bus(),
        user_text="帮我将内容转成md文件",
    )
    token = set_todo_runtime(runtime)
    try:
        assert office_writes_blocked() is True
        assert is_office_write_command("officecli create /tmp/a.docx")
        assert not is_office_write_command("officecli view /tmp/a.docx outline")
    finally:
        reset_todo_runtime(token)
