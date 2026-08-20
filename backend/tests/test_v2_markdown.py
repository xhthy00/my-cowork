from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.runtime.v2.markdown import (
    maybe_write_markdown_report,
    markdown_filename,
    wants_markdown_report,
)


def test_wants_markdown_for_research_not_office():
    assert wants_markdown_report("调研扬州最新购房政策")
    assert not wants_markdown_report("写一份关于增加项目经费的请示")
    assert not wants_markdown_report("Python 里 list 和 tuple 的区别")
    assert wants_markdown_report("帮我生成md文档")
    assert wants_markdown_report("整理算法备案流程内容并生成markdown文档")
    assert not wants_markdown_report("做成一份报告")
    assert not wants_markdown_report("写一份报告")


def test_markdown_filename_strips_unsafe():
    assert markdown_filename("调研扬州最新购房政策").endswith(".md")
    assert "/" not in markdown_filename("a/b")


def test_writes_markdown_into_workdir(tmp_path):
    policy = (
        "扬州目前已全面取消限购、限售，门槛处于历史最宽松阶段。"
        "最新文件是扬建房〔2026〕9号，有效期至2026年12月31日。"
        "公积金贷款额度阶段性上调，人才安家券最高可抵扣首付。"
        "外地户籍家庭可与本地家庭一样直接购买商品房。"
    )
    messages = [
        HumanMessage(content="调研扬州最新购房政策"),
        AIMessage(content=policy),
    ]
    out, path = maybe_write_markdown_report(
        "调研扬州最新购房政策", messages, workdir=tmp_path
    )
    assert path
    written = tmp_path / "调研扬州最新购房政策.md"
    assert written.is_file()
    assert "取消限购" in written.read_text(encoding="utf-8")
    assert any("已整理为 Markdown" in str(getattr(m, "content", "")) for m in out)


def test_skips_when_fs_write_already_wrote_md(tmp_path):
    policy = "扬州目前已全面取消限购、限售。" * 8
    messages = [
        HumanMessage(content="调研扬州最新购房政策"),
        AIMessage(content=policy),
        ToolMessage(
            content=f"Wrote 1200 characters to {tmp_path / '已有.md'}",
            tool_call_id="c1",
            name="fs_write",
        ),
    ]
    out, path = maybe_write_markdown_report(
        "调研扬州最新购房政策", messages, workdir=tmp_path
    )
    assert path is None
    assert out == messages
