from langchain_core.messages import AIMessage, ToolMessage

from app.graphs.routing import (
    document_tools_succeeded,
    has_office_deliverable,
    wants_document,
    wants_file_document,
    wants_markdown_file,
    wants_pptx,
    wants_unspecified_document,
)


def test_wants_document_generation_intent():
    assert wants_document("帮我生成一份旅游攻略PPT")
    assert not wants_document("做成一份报告")
    assert wants_unspecified_document("做成一份报告")
    assert wants_file_document("做成一份报告")
    assert wants_document("整理宜昌旅游攻略 word 版本发我")
    assert wants_document("把行程做成word版")
    assert wants_document("写一份 Word 报告")
    assert not wants_unspecified_document("写一份 Word 报告")
    assert wants_unspecified_document("写一份报告")
    assert not wants_document("写一份报告")
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


def test_extract_claimed_office_paths_ignores_urls():
    from app.graphs.routing import extract_claimed_office_paths

    text = (
        "备案材料见 https://www.doc 以及 https://www.document.gov.cn/guide.docx。\n"
        "也可参考 http://example.com/a.pdf\n"
    )
    assert extract_claimed_office_paths(text) == []
    assert extract_claimed_office_paths("见 //www.doc 说明") == []


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
    assert not wants_document("调研扬州最新购房政策")
    assert not wants_document("大模型备案是什么流程")
    assert not wants_document("帮我生成md文档")
    assert not wants_document("生成一份 markdown")
    assert not wants_document("写成 .md 文件")
    assert wants_markdown_file("帮我生成md文档")
    assert not wants_unspecified_document("帮我生成md文档")
    assert wants_document("生成md文档再出一份 word 版")


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


def test_document_tools_officecli_help_does_not_count():
    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "bash",
                        "args": {"cmd": "officecli --version"},
                        "id": "c1",
                        "type": "tool_call",
                    }
                ],
            ),
            ToolMessage(
                content="officecli 1.0.144 is ready\nSee officecli create report.docx",
                tool_call_id="c1",
                name="bash",
            ),
        ]
    }
    assert not document_tools_succeeded(state)


def test_looks_like_workspace_dump():
    from app.runtime.context import looks_like_plan_only, looks_like_workspace_dump

    dump = (
        "Working Directory: e950532f\n"
        "Final Output Directory: /Users/me/runs/x\n"
        "officecli 1.0.144 is ready\n"
        "Execution Plan: Batch 1 Cover"
    )
    assert looks_like_workspace_dump(dump)
    assert looks_like_plan_only("整理宜昌旅游攻略 word 版本发我", dump)
    assert not looks_like_workspace_dump("已生成宜昌旅游攻略.docx，含景点与行程。")
    jargon = (
        "基于 transcript 中可见的操作记录完成了 Word。"
        "出现多次 Heading2 段落（paraId 00100093）。"
    )
    assert looks_like_workspace_dump(jargon)
    delivery = (
        "已完成。Word 版调研报告已写入：\n"
        "交付摘要\n文件规格：15 KB · 通过 schema 校验。"
    )
    assert looks_like_workspace_dump(delivery)
    from app.runtime.context import looks_like_process_narration, is_user_facing_answer

    assert looks_like_process_narration("Now let me set up page layout and build the cover page.")
    assert not is_user_facing_answer("我来调研扬州最新购房政策。先并行搜索几个关键方向。")
    assert is_user_facing_answer("扬州目前已全面取消限购、限售，门槛处于历史最宽松阶段。")


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
