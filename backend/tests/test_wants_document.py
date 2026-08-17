from langchain_core.messages import AIMessage, ToolMessage

from app.graphs.routing import (
    document_tools_succeeded,
    has_office_deliverable,
    wants_document,
    wants_pptx,
)


def test_wants_document_generation_intent():
    assert wants_document("帮我生成一份旅游攻略PPT")
    assert wants_document("做成一份报告")
    assert wants_pptx("请做一份 pptx")


def test_wants_document_xlsx_estimate():
    assert wants_document("帮我做一份200P算力中心建设投资估算")
    assert wants_document("生成xlsx投资估算表")
    assert wants_document("做一份投资估算 Excel")


def test_extract_claimed_office_paths():
    from app.graphs.routing import extract_claimed_office_paths

    text = (
        "交付文件\n"
        "/Users/tanghaoyu/Documents/AIS/200P算力中心建设投资估算.xlsx\n"
    )
    paths = extract_claimed_office_paths(text)
    assert paths == [
        "/Users/tanghaoyu/Documents/AIS/200P算力中心建设投资估算.xlsx"
    ]


def test_wants_document_gongwen_regenerate():
    assert wants_document("#official-document-writing 帮我重新生成一份上述内容的公文汇报")
    assert wants_document("帮我重新生成一份上述内容的公文汇报")
    assert wants_document("写一份关于增加项目经费的请示")
    assert wants_document("帮我起草一份部门周例会通知")


def test_wants_document_not_mere_mention():
    assert not wants_document("帮我解读一下该文档的核心内容")
    assert not wants_document(
        "解读\n\n[附件: /Users/me/方案.docx]"
    )
    assert not wants_document("这个 pdf 里写了什么")
    assert not wants_document("按公文质量清单检查这份通知初稿，并给出修改建议")


def test_document_tools_docx_gen_counts():
    state = {
        "messages": [
            ToolMessage(
                content="/tmp/out/汇报.docx",
                tool_call_id="c1",
                name="docx_gen",
            )
        ]
    }
    assert document_tools_succeeded(state)


def test_document_tools_officecli_bash_counts():
    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "bash",
                        "args": {"cmd": "officecli create /tmp/out/汇报.docx"},
                        "id": "c1",
                        "type": "tool_call",
                    }
                ],
            ),
            ToolMessage(
                content='{"ok": true, "path": "/tmp/out/汇报.docx", "error": null}',
                tool_call_id="c1",
                name="bash",
            ),
        ]
    }
    assert document_tools_succeeded(state)


def test_document_tools_load_skill_or_gongwen_format_not_enough():
    load_only = {
        "messages": [
            ToolMessage(
                content="## Skill: docx\nCreate documents with docx-js.",
                tool_call_id="c1",
                name="load_skill",
            )
        ]
    }
    assert not document_tools_succeeded(load_only)

    restyle_only = {
        "messages": [
            ToolMessage(
                content="/tmp/out/旧稿.docx",
                tool_call_id="c2",
                name="docx_gongwen_format",
            )
        ]
    }
    assert not document_tools_succeeded(restyle_only)


def test_has_office_deliverable():
    assert has_office_deliverable(["/tmp/a.docx"])
    assert not has_office_deliverable(["/tmp/a.txt"])
    assert has_office_deliverable(["/tmp/a.pptx"], require_pptx=True)
    assert not has_office_deliverable(["/tmp/a.docx"], require_pptx=True)
