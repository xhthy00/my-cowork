"""Tests for Eigent-aligned Progress planner."""

import pytest

from app.runtime.todo_planner import (
    advance_todos,
    apply_todo_write,
    normalize_todos,
    parse_todos_json,
    pick_todo_for_worker,
    plan_todos,
    plan_todos_llm,
    without_office_todos,
)


def test_normalize_enforces_one_in_progress():
    todos = normalize_todos(
        [
            {"content": "Research policy", "active_form": "Researching policy", "status": "pending"},
            {"content": "Write report", "active_form": "Writing report", "status": "pending"},
        ]
    )
    assert len(todos) == 2
    assert todos[0]["id"] == "todo_1"
    assert todos[0]["status"] == "in_progress"
    assert todos[1]["status"] == "pending"


def test_parse_todos_json_from_fenced_output():
    raw = """```json
[
  {"content": "检索文档技能", "active_form": "正在检索文档技能", "status": "in_progress"},
  {"content": "研究备案政策与流程", "active_form": "正在研究备案政策与流程", "status": "pending"},
  {"content": "撰写并校验文档", "active_form": "正在撰写并校验文档", "status": "pending"},
  {"content": "输出文档文件", "active_form": "正在输出文档文件", "status": "pending"}
]
```"""
    todos = parse_todos_json(raw)
    assert len(todos) == 4
    assert todos[0]["content"] == "检索文档技能"
    assert todos[0]["status"] == "in_progress"


def test_todo_write_replaces_list():
    todos = apply_todo_write(
        [
            {"content": "A", "active_form": "Doing A", "status": "completed"},
            {"content": "B", "active_form": "Doing B", "status": "in_progress"},
        ]
    )
    assert [t["content"] for t in todos] == ["A", "B"]
    assert todos[1]["status"] == "in_progress"


def test_fallback_generic_not_domain_template():
    todos = plan_todos(
        "帮我生成一份关于大模型、算法备案流程的研究文档",
        session_mode="single-agent",
    )
    # Fallback is generic — LLM path owns Eigent-style domain splits
    contents = " ".join(t["content"] for t in todos)
    assert "拆解" in contents or "执行" in contents or "交付" in contents
    assert "Finished doc_worker" not in contents


def test_advance_and_pick_worker():
    todos = normalize_todos(
        [
            {"content": "Step 1", "active_form": "Doing 1", "status": "in_progress"},
            {"content": "Step 2", "active_form": "Doing 2", "status": "pending"},
        ]
    )
    focus = pick_todo_for_worker(todos, "document_agent")
    assert focus == "todo_2" or focus == "todo_1"
    updated = advance_todos(todos, next_in_progress_id="todo_2")
    running = [t for t in updated if t["status"] == "in_progress"]
    assert len(running) == 1
    assert running[0]["id"] == "todo_2"


def test_without_office_todos_drops_docx_steps():
    todos = normalize_todos(
        [
            {"content": "检索备案政策", "active_form": "正在检索备案政策", "status": "pending"},
            {
                "content": "调用 officecli 生成 .docx",
                "active_form": "正在生成文档",
                "status": "pending",
            },
            {"content": "在对话中回答", "active_form": "正在整理回答", "status": "pending"},
        ]
    )
    kept = without_office_todos(todos)
    assert [t["content"] for t in kept] == ["检索备案政策", "在对话中回答"]


@pytest.mark.asyncio
async def test_plan_todos_llm_rejects_office_on_research_question():
    import json

    class _LLM:
        async def ainvoke(self, _messages):
            return type(
                "M",
                (),
                {
                    "content": json.dumps(
                        [
                            {
                                "content": "检查 officecli 是否可用",
                                "active_form": "正在检查 officecli",
                                "status": "in_progress",
                            },
                            {
                                "content": "调用 officecli 生成 .docx 到 AIS",
                                "active_form": "正在生成文档",
                                "status": "pending",
                            },
                            {
                                "content": "核对文件路径与大小",
                                "active_form": "正在核对文件",
                                "status": "pending",
                            },
                        ],
                        ensure_ascii=False,
                    )
                },
            )()

    todos = await plan_todos_llm(
        "大模型备案是什么流程",
        _LLM(),
        session_mode="single-agent",
    )
    blob = " ".join(t["content"] for t in todos).lower()
    assert "officecli" not in blob
    assert ".docx" not in blob
    assert todos
    assert any("拆解" in t["content"] or "执行" in t["content"] or "交付" in t["content"] for t in todos)
