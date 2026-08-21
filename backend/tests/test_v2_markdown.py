from langchain_core.messages import AIMessage, HumanMessage

from app.runtime.v2.markdown import maybe_write_markdown_report, wants_markdown_report


def test_runtime_never_auto_writes_markdown(tmp_path):
    """Eigent: files come from write_to_file only — no chat-summary .md."""
    assert not wants_markdown_report("调研扬州最新购房政策")
    assert not wants_markdown_report("帮我生成md文档")
    assert not wants_markdown_report("帮我整合成数据分析html")
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
    assert path is None
    assert out == messages
    assert not list(tmp_path.glob("*.md"))
