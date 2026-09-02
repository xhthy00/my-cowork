"""Prompt files loaded via load_prompt."""

from pathlib import Path

from app.agents.factory import load_prompt

PROMPTS = Path(__file__).resolve().parents[1] / "app" / "agents" / "prompts"

REQUIRED = (
    "single_agent",
    "developer",
    "document",
    "browser",
    "multi_modal",
    "planner",
    "todo_planner",
    "worker_brief",
    "critic",
    "synthesize",
    "coordinator",
    "compact",
    "skills_system",
    "local_constraints",
)


def test_required_prompts_exist():
    for name in REQUIRED:
        text = load_prompt(name)
        assert text.strip(), name
        assert (PROMPTS / f"{name}.md").is_file()


def test_planner_does_not_hide_parent_task():
    text = load_prompt("planner")
    assert "每个子任务必须自包含（执行者不知道父任务全文）" not in text
    assert "工人会同时看到父任务全文" in text


def test_placeholder_replace_keeps_json_braces():
    text = load_prompt("planner", user_text="X")
    assert "{" in text and "}" in text


def test_browser_mentions_web_search():
    text = load_prompt("browser")
    assert "web_search" in text
    assert "web_fetch" in text
    assert "STOP CONDITION" in text


def test_planner_caps_research_split():
    text = load_prompt("planner")
    assert "最多 2 个 browser_agent" in text
    assert "禁止要求" in text


def test_single_agent_forbids_search_preamble():
    text = load_prompt("single_agent")
    assert "web_search" in text
    assert "我先搜一下" in text
    assert "paraId" in text
    assert "MUST NOT answer from your own knowledge" in text
    assert "no specified format" in text
    assert "HTML file" in text
    assert "write_to_file" in text
    assert "Write only that one file" in text
    assert "Loading officecli skill" in text
    assert "Simplified Chinese" in text
    assert "list_note" in text
    assert "shared_files" in text
    assert "structured Markdown" in text
    assert "_scratch" not in text


def test_local_constraints_notes_not_scratch():
    text = load_prompt("local_constraints")
    assert "create_note" in text
    assert "shared_files" in text
    assert "Intermediate/scratch files go under `_scratch/`" not in text
    assert "deleted when the task ends" not in text
    assert "清空 `_scratch`" not in text


def test_document_prompt_html_default():
    text = load_prompt("document")
    assert "no specified format" in text
    assert "write_to_file" in text
    assert "HTML file" in text
    assert "fs_write" in text


def test_skills_system_office_opt_in():
    text = load_prompt("skills_system")
    assert "{{pdf}}" in text or "{{data-analyzer}}" in text
    assert "do not also write .docx" in text
    assert "MUST use the skill workflow first" in text


def test_synthesize_prompt_forbids_internal_jargon():
    text = load_prompt("synthesize", user_text="x", evidence="y")
    assert "paraId" in text
    assert "Never mention" in text
    assert "{transcript}" not in text
    assert "unless the user asked for a table" not in text
    assert "tables or lists" in text.lower() or "Use tables" in text
    assert "来源" in text


def test_assemble_merges_assistant_rules_into_one_system(monkeypatch):
    from langchain_core.messages import SystemMessage

    from app.runtime.v2.assemble import assemble_system_messages

    monkeypatch.setattr(
        "app.assistants.get_assistant",
        lambda _aid: {"rules": "prefer officecli"},
    )
    msgs = assemble_system_messages(
        agent_prompt_name="single_agent",
        assistant_id="ppt-creator",
        long_term=object(),
    )
    assert len(msgs) == 1
    assert isinstance(msgs[0], SystemMessage)
    assert "prefer officecli" in msgs[0].content


def test_assemble_skips_office_skill_preload_on_unspecified_report(monkeypatch):
    from app.runtime.v2.assemble import assemble_system_messages

    monkeypatch.setattr(
        "app.runtime.v2.assemble._skill_block",
        lambda sid: f"PRELOADED:{sid}",
    )
    msgs = assemble_system_messages(
        agent_prompt_name="single_agent",
        enabled_skill_ids=["officecli-docx", "demo"],
        user_text="做成一份报告",
        long_term=object(),
    )
    blob = msgs[0].content
    assert "PRELOADED:officecli-docx" not in blob
    assert "PRELOADED:demo" in blob


def test_assemble_skips_office_skill_preload_on_research(monkeypatch):
    from app.runtime.v2.assemble import assemble_system_messages

    monkeypatch.setattr(
        "app.runtime.v2.assemble._skill_block",
        lambda sid: f"PRELOADED:{sid}",
    )
    msgs = assemble_system_messages(
        agent_prompt_name="single_agent",
        enabled_skill_ids=["officecli-docx", "demo"],
        user_text="调研扬州最新购房政策",
        long_term=object(),
    )
    blob = msgs[0].content
    assert "PRELOADED:officecli-docx" not in blob
    assert "PRELOADED:demo" in blob


def test_assemble_skips_office_skill_preload_on_markdown_file(monkeypatch):
    from app.runtime.v2.assemble import assemble_system_messages

    monkeypatch.setattr(
        "app.runtime.v2.assemble._skill_block",
        lambda sid: f"PRELOADED:{sid}",
    )
    msgs = assemble_system_messages(
        agent_prompt_name="single_agent",
        enabled_skill_ids=["officecli-docx", "demo"],
        user_text="帮我将内容转成md文件",
        long_term=object(),
    )
    blob = msgs[0].content
    assert "PRELOADED:officecli-docx" not in blob
    assert "PRELOADED:demo" in blob


def test_assemble_preloads_office_skill_when_user_wants_doc(monkeypatch):
    from app.runtime.v2.assemble import assemble_system_messages

    monkeypatch.setattr(
        "app.runtime.v2.assemble._skill_block",
        lambda sid: f"PRELOADED:{sid}",
    )
    msgs = assemble_system_messages(
        agent_prompt_name="single_agent",
        enabled_skill_ids=["officecli-docx"],
        user_text="写一份 Word 报告",
        long_term=object(),
    )
    assert "PRELOADED:officecli-docx" in msgs[0].content


def test_assemble_preloads_office_skill_on_hash_tag(monkeypatch):
    from app.runtime.v2.assemble import assemble_system_messages

    monkeypatch.setattr(
        "app.runtime.v2.assemble._skill_block",
        lambda sid: f"PRELOADED:{sid}",
    )
    msgs = assemble_system_messages(
        agent_prompt_name="single_agent",
        enabled_skill_ids=["officecli-docx"],
        user_text="形成word #officecli-docx",
        long_term=object(),
    )
    assert "PRELOADED:officecli-docx" in msgs[0].content


def test_assemble_auto_preloads_officecli_when_user_asks_word(monkeypatch):
    from app.runtime.v2.assemble import assemble_system_messages

    monkeypatch.setattr(
        "app.runtime.v2.assemble._skill_block",
        lambda sid: f"PRELOADED:{sid}",
    )
    msgs = assemble_system_messages(
        agent_prompt_name="single_agent",
        enabled_skill_ids=[],
        user_text="帮我生成word文档",
        long_term=object(),
    )
    blob = msgs[0].content
    assert "PRELOADED:officecli" in blob
    assert "PRELOADED:officecli-docx" in blob


def test_assemble_injects_bound_knowledge_block():
    from app.runtime.v2.assemble import assemble_system_messages

    msgs = assemble_system_messages(
        agent_prompt_name="single_agent",
        knowledge_bases=[{"id": "kb1", "name": "唐浩宇的知识库", "source": "ima"}],
        user_text="总体集成甲级资质要多少资本",
        long_term=object(),
    )
    blob = msgs[0].content
    assert "<bound_knowledge>" in blob
    assert "knowledge_base_id=kb1" in blob
    assert "唐浩宇的知识库" in blob
    assert "ima_search_knowledge" in blob
    assert "在知识库里搜" in blob


def test_normalize_knowledge_bases_drops_junk():
    from app.runtime.v2.assemble import normalize_knowledge_bases

    rows = normalize_knowledge_bases(
        [
            {"id": "kb1", "name": "A"},
            {"id": "kb1", "name": "dup"},
            {"name": ""},
            "x",
        ]
    )
    assert rows == [{"id": "kb1", "name": "A", "source": "ima"}]
