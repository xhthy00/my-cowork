"""v2 critic + compact."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.runtime.v2.compact import compact_messages, split_keep_recent
from app.runtime.v2.critic import (
    TaskAnalysisResult,
    analyze_task,
    evidence_gate,
    finalize_worker_result,
    heuristic_critic,
)


def test_critic_rejects_plan_only():
    v = heuristic_critic(
        "大数据集团介入需要注意哪些",
        [
            HumanMessage(content="大数据集团介入需要注意哪些"),
            AIMessage(
                content="I will generate a formal consultation analysis report (docx). Plan the task first."
            ),
        ],
    )
    assert v.next == "act"
    assert v.missing


def test_critic_rejects_unsearched_policy():
    v = heuristic_critic(
        "调研某地最新购房政策",
        [
            HumanMessage(content="调研某地最新购房政策"),
            AIMessage(content="限购已经取消。"),
        ],
    )
    assert v.next == "act"
    assert any("web_search" in m for m in v.missing)
    assert evidence_gate(
        "调研某地最新购房政策",
        [
            HumanMessage(content="调研某地最新购房政策"),
            AIMessage(content="限购已经取消。"),
        ],
    ).next == "act"


def test_critic_rejects_yangzhou_search_preamble():
    user = "调研扬州最新购房政策"
    v = heuristic_critic(
        user,
        [HumanMessage(content=user), AIMessage(content="我先搜一下扬州最新购房政策的相关信息。")],
    )
    assert v.next == "act"
    assert any("web_search" in m for m in v.missing)


def _research_ok_messages(user: str, answer: str) -> list:
    u1, u2 = "https://example.gov/a", "https://example.gov/b"
    return [
        HumanMessage(content=user),
        AIMessage(
            content="",
            tool_calls=[{"id": "c1", "name": "web_search", "args": {"query": user + " 官方"}}],
        ),
        ToolMessage(
            content=f'[{{"title":"a","url":"{u1}","snippet":"x"}}]',
            tool_call_id="c1",
            name="web_search",
        ),
        AIMessage(
            content="",
            tool_calls=[{"id": "c2", "name": "web_search", "args": {"query": user + " 细则"}}],
        ),
        ToolMessage(
            content=f'[{{"title":"b","url":"{u2}","snippet":"y"}}]',
            tool_call_id="c2",
            name="web_search",
        ),
        AIMessage(
            content="",
            tool_calls=[{"id": "c3", "name": "web_fetch", "args": {"url": u1}}],
        ),
        ToolMessage(content=f"URL: {u1}\n\n正文甲", tool_call_id="c3", name="web_fetch"),
        AIMessage(
            content="",
            tool_calls=[{"id": "c4", "name": "web_fetch", "args": {"url": u2}}],
        ),
        ToolMessage(content=f"URL: {u2}\n\n正文乙", tool_call_id="c4", name="web_fetch"),
        AIMessage(content=answer + f" 来源 {u1} {u2}"),
    ]


def test_critic_rejects_search_without_fetch():
    v = heuristic_critic(
        "调研某地最新购房政策",
        [
            HumanMessage(content="调研某地最新购房政策"),
            AIMessage(
                content="",
                tool_calls=[{"id": "c1", "name": "web_search", "args": {"query": "购房政策"}}],
            ),
            ToolMessage(
                content='[{"url":"https://example.gov"}]',
                tool_call_id="c1",
                name="web_search",
            ),
            AIMessage(content="根据检索，政策有调整。来源见工具结果。"),
        ],
    )
    assert v.next == "act"
    assert not v.sources_ok
    assert any("web_fetch" in m for m in v.missing)


def test_critic_accepts_search_and_fetch_backed_answer():
    user = "调研某地最新购房政策"
    v = heuristic_critic(
        user,
        _research_ok_messages(user, "限购已放宽，首付不低于 15%。"),
    )
    assert v.next == "answer"
    assert v.sources_ok


def test_critic_browser_requires_findings_note():
    user = "调研某地最新购房政策"
    msgs = _research_ok_messages(user, "限购已放宽，首付不低于 15%。")
    v = heuristic_critic(user, msgs, require_findings=True)
    assert v.next == "act"
    assert any("findings" in m for m in v.missing)
    msgs.append(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "n1",
                    "name": "append_note",
                    "args": {"name": "findings", "content": "限购已放宽 https://example.gov/a"},
                }
            ],
        )
    )
    msgs.append(
        ToolMessage(
            content="Appended to note findings", tool_call_id="n1", name="append_note"
        )
    )
    v2 = heuristic_critic(user, msgs, require_findings=True)
    assert v2.next == "answer"


def test_critic_browser_rejects_thin_findings_without_url():
    user = "调研某地最新购房政策"
    msgs = _research_ok_messages(user, "限购已放宽，首付不低于 15%。")
    msgs.append(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "n1",
                    "name": "append_note",
                    "args": {"name": "findings", "content": "限购已放宽"},
                }
            ],
        )
    )
    msgs.append(
        ToolMessage(
            content="Appended to note findings", tool_call_id="n1", name="append_note"
        )
    )
    v = heuristic_critic(user, msgs, require_findings=True)
    assert v.next == "act"
    assert any("findings" in m for m in v.missing)


def test_critic_ignores_trailing_word_delivery():
    user = "调研扬州最新购房政策"
    policy = (
        "扬州目前已全面取消限购、限售，门槛处于历史最宽松阶段。"
        "最新文件是扬建房〔2026〕9号，有效期至2026年12月31日。"
    )
    msgs = _research_ok_messages(user, policy)
    msgs.append(
        AIMessage(content="已完成。Word 版调研报告已写入。\n交付摘要\n文件规格：15 KB")
    )
    v = heuristic_critic(user, msgs)
    assert v.next == "answer"


def test_critic_accepts_short_python_qa():
    user = "Python 里 list 和 tuple 的区别是什么？"
    answer = "list 可变，tuple 不可变。list 用方括号，tuple 用圆括号。"
    v = heuristic_critic(
        user,
        [HumanMessage(content=user), AIMessage(content=answer)],
    )
    assert v.next == "answer"
    assert v.user_facing_complete


def test_critic_rejects_unspecified_report_without_html():
    v = heuristic_critic(
        "做成一份报告",
        [
            HumanMessage(content="做成一份报告"),
            AIMessage(content="报告正文如下……"),
        ],
    )
    assert v.next == "act"
    assert any("HTML" in m for m in v.missing)


def test_critic_accepts_unspecified_report_html_write():
    v = heuristic_critic(
        "做成一份报告",
        [
            HumanMessage(content="做成一份报告"),
            AIMessage(
                content="",
                tool_calls=[{"id": "c1", "name": "fs_write", "args": {"path": "/tmp/a.html"}}],
            ),
            ToolMessage(
                content="Wrote 800 characters to /tmp/a.html",
                tool_call_id="c1",
                name="fs_write",
            ),
            AIMessage(content="已写入 HTML 报告：/tmp/a.html"),
        ],
    )
    assert v.next == "answer"


def test_critic_rejects_missing_office_file():
    v = heuristic_critic(
        "写一份关于增加项目经费的请示",
        [
            HumanMessage(content="写一份关于增加项目经费的请示"),
            AIMessage(content="请示正文如下……"),
        ],
    )
    assert v.next == "act"


@pytest.mark.asyncio
async def test_analyze_skips_llm_when_floor_fails():
    class BoomLLM:
        async def ainvoke(self, *_args, **_kwargs):
            raise AssertionError("LLM must not run when the completeness floor fails")

    result = await analyze_task(
        "写一份关于增加项目经费的请示",
        "请示正文如下……",
        llm=BoomLLM(),
        user_text="写一份关于增加项目经费的请示",
    )
    assert result.quality_score == 0
    assert result.recovery_strategy == "retry"


@pytest.mark.asyncio
async def test_analyze_research_does_not_fail_open():
    class BoomLLM:
        async def ainvoke(self, *_args, **_kwargs):
            raise RuntimeError("no structured output")

    user = "调研扬州最新购房政策"
    msgs = _research_ok_messages(user, "限购已放宽。")
    result = await analyze_task(
        user,
        "限购已放宽。来源 https://example.gov/a https://example.gov/b",
        llm=BoomLLM(),
        user_text=user,
        messages=msgs,
    )
    assert result.quality_score == 0
    assert result.recovery_strategy == "retry"


@pytest.mark.asyncio
async def test_analyze_fail_open_when_quality_llm_breaks():
    class BoomLLM:
        async def ainvoke(self, *_args, **_kwargs):
            raise RuntimeError("no structured output")

    user = "Python 里 list 和 tuple 的区别"
    answer = "list 可变，tuple 不可变。"
    result = await analyze_task(
        user,
        answer,
        llm=BoomLLM(),
        user_text=user,
        messages=[HumanMessage(content=user), AIMessage(content=answer)],
    )
    assert result.quality_score == 80
    assert result.recovery_strategy is None


@pytest.mark.asyncio
async def test_analyze_low_score_retries():
    class ScoreLLM:
        async def ainvoke(self, *_args, **_kwargs):
            return type(
                "M",
                (),
                {
                    "content": (
                        '{"quality_score": 40, "reasoning": "thin",'
                        ' "issues": ["more detail"], "recovery_strategy": "retry"}'
                    )
                },
            )()

    user = "Python 里 list 和 tuple 的区别"
    answer = "list 可变，tuple 不可变。"
    result = await analyze_task(
        user,
        answer,
        llm=ScoreLLM(),
        user_text=user,
        messages=[HumanMessage(content=user), AIMessage(content=answer)],
    )
    assert result.quality_score == 40
    assert result.recovery_strategy == "retry"


@pytest.mark.asyncio
async def test_analyze_high_score_clears_recovery():
    class ScoreLLM:
        async def ainvoke(self, *_args, **_kwargs):
            return type(
                "M",
                (),
                {
                    "content": (
                        '{"quality_score": 90, "reasoning": "ok",'
                        ' "issues": [], "recovery_strategy": "retry"}'
                    )
                },
            )()

    user = "Python 里 list 和 tuple 的区别"
    answer = "list 可变，tuple 不可变。"
    result = await analyze_task(
        user,
        answer,
        llm=ScoreLLM(),
        user_text=user,
        messages=[HumanMessage(content=user), AIMessage(content=answer)],
    )
    assert result.quality_score == 90
    assert result.recovery_strategy is None


def test_finalize_retry_then_halt_at_max():
    task = {"id": "t1", "content": "do it", "retries": 0}
    analysis = TaskAnalysisResult(quality_score=0, recovery_strategy="retry")
    patch = finalize_worker_result(task=task, summary="thin", analysis=analysis, max_retries=3)
    assert patch["status"] == "waiting"
    assert patch["retries"] == 1

    halted = finalize_worker_result(
        task={"id": "t1", "content": "do it", "retries": 3},
        summary="thin",
        analysis=analysis,
        max_retries=3,
    )
    assert halted["status"] == "failed"


@pytest.mark.asyncio
async def test_coordinate_without_llm_finishes_terminal_failed():
    from app.graphs.coordinator import coordinate

    decision = await coordinate(
        "q",
        [{"id": "t1", "status": "failed", "content": "x", "retries": 3}],
        llm=None,
    )
    assert decision["action"] == "finish"
    assert decision["rework"] == []


@pytest.mark.asyncio
async def test_analyze_empty_result_retries_without_llm():
    class BoomLLM:
        async def ainvoke(self, *_args, **_kwargs):
            raise AssertionError("empty result must not call the analysis LLM")

    result = await analyze_task("do it", "", llm=BoomLLM(), for_failure=True)
    assert result.recovery_strategy == "retry"
    assert result.quality_score == 0


def test_finalize_replan_rewrites_brief():
    patch = finalize_worker_result(
        task={"id": "t1", "content": "vague", "retries": 0},
        summary="not enough",
        analysis=TaskAnalysisResult(
            quality_score=40,
            recovery_strategy="replan",
            modified_task_content="Write a 3-point Chinese answer.",
        ),
        max_retries=3,
    )
    assert patch["status"] == "waiting"
    assert patch["content"] == "Write a 3-point Chinese answer."


@pytest.mark.asyncio
async def test_compact_keeps_recent_human_turns():
    msgs = []
    for i in range(6):
        msgs.append(HumanMessage(content=f"u{i}"))
        msgs.append(
            ToolMessage(content=f"old-tool-{i} " + "x" * 50, tool_call_id=str(i), name="web_search")
        )
        msgs.append(AIMessage(content=f"a{i}"))
    older, recent = split_keep_recent(msgs, keep_turns=3)
    assert older
    assert any(getattr(m, "content", "") == "u3" for m in recent)
    compacted = await compact_messages(msgs, threshold=10, keep_turns=3)
    assert compacted
    assert any(
        "Earlier work" in str(getattr(m, "content", "")) or getattr(m, "type", "") == "system"
        for m in compacted[:2]
    )


@pytest.mark.asyncio
async def test_synthesize_keeps_pure_qa_without_rewrite():
    from app.runtime.v2.synthesize import synthesize_answer

    class BoomLLM:
        async def ainvoke(self, *_args, **_kwargs):
            raise AssertionError("pure Q&A must not be rewritten")

    user = "Python 里 list 和 tuple 的区别"
    answer = "list 可变，tuple 不可变。"
    text = await synthesize_answer(
        user,
        [HumanMessage(content=user), AIMessage(content=answer)],
        llm=BoomLLM(),
    )
    assert text == answer


@pytest.mark.asyncio
async def test_synthesize_replaces_transcript_jargon_with_search_digest():
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from app.runtime.v2.synthesize import synthesize_answer

    class JargonLLM:
        async def ainvoke(self, *_args, **_kwargs):
            return AIMessage(
                content="基于 transcript 中可见的操作记录，Heading2 paraId 00100093。"
            )

    user = "调研扬州最新购房政策"
    text = await synthesize_answer(
        user,
        [
            HumanMessage(content=user),
            AIMessage(
                content="",
                tool_calls=[{"id": "c1", "name": "web_search", "args": {"query": user}}],
            ),
            ToolMessage(
                content='[{"title":"扬州购房","url":"https://yangzhou.gov.cn/p","snippet":"限购已放宽"}]',
                tool_call_id="c1",
                name="web_search",
            ),
            AIMessage(
                content="基于 transcript 完成 Word。Heading2 paraId 00100093。"
            ),
        ],
        llm=JargonLLM(),
        rewrite=True,
    )
    assert "paraId" not in text
    assert "transcript" not in text.lower()
    assert "Heading2" not in text
    assert "限购" in text or "yangzhou.gov.cn" in text


def test_evidence_blob_drops_officecli_para_ids():
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from app.runtime.v2.synthesize import evidence_blob

    blob = evidence_blob(
        [
            HumanMessage(content="调研扬州最新购房政策"),
            ToolMessage(
                content='[{"title":"政策","url":"https://yangzhou.gov.cn","snippet":"限购放宽"}]',
                tool_call_id="c1",
                name="web_search",
            ),
            ToolMessage(
                content='{"ok":true,"paraId":"00100093","style":"Heading2"}',
                tool_call_id="c2",
                name="bash",
            ),
            AIMessage(content="基于 transcript，Heading2 paraId 00100093"),
        ]
    )
    assert "yangzhou.gov.cn" in blob
    assert "00100093" not in blob
    assert "Heading2" not in blob
    assert "transcript" not in blob.lower()


def test_evidence_blob_puts_fetch_before_search():
    from langchain_core.messages import HumanMessage, ToolMessage

    from app.runtime.v2.synthesize import evidence_blob

    blob = evidence_blob(
        [
            HumanMessage(content="调研"),
            ToolMessage(
                content='[{"url":"https://example.gov/a","snippet":"snippet-only"}]',
                tool_call_id="c1",
                name="web_search",
            ),
            ToolMessage(
                content="URL: https://example.gov/a\n\nPAGE_BODY_LIMIT_PURCHASE",
                tool_call_id="c2",
                name="web_fetch",
            ),
        ]
    )
    assert blob.index("PAGE_BODY_LIMIT_PURCHASE") < blob.index("snippet-only")


@pytest.mark.asyncio
async def test_synthesize_research_keeps_complete_answer():
    from langchain_core.messages import AIMessage

    from app.runtime.v2.synthesize import synthesize_answer

    class BoomLLM:
        async def ainvoke(self, *_args, **_kwargs):
            raise AssertionError("complete research answers must not be rewritten")

    user = "调研扬州最新购房政策"
    answer = "扬州限购已放宽。来源 https://example.gov/a"
    text = await synthesize_answer(
        user,
        _research_ok_messages(user, answer),
        llm=BoomLLM(),
    )
    assert "限购" in text
    assert "终稿" not in text


@pytest.mark.asyncio
async def test_compose_workforce_keeps_worker_summary():
    from app.runtime.v2.synthesize import compose_workforce_answer

    class BoomLLM:
        async def ainvoke(self, *_args, **_kwargs):
            raise AssertionError("substantial worker summary must not be rewritten")

    body = (
        "扬州目前已全面取消限购、限售，门槛处于历史最宽松阶段。"
        "最新文件是扬建房〔2026〕9号，有效期至2026年12月31日。"
        "来源 https://example.gov/a"
    )
    text = await compose_workforce_answer(
        "调研扬州最新购房政策",
        subtasks=[{"id": "task_1", "result": f"<summary>{body}</summary>"}],
        messages=[],
        llm=BoomLLM(),
    )
    assert "限购" in text
    assert "扬建房" in text


@pytest.mark.asyncio
async def test_compose_workforce_rewrites_thin_when_fetch_exists():
    from app.runtime.v2.synthesize import compose_workforce_answer

    called: list[int] = []

    class Cap:
        async def ainvoke(self, *_args, **_kwargs):
            called.append(1)
            return AIMessage(content="合成后的扬州限购要点。来源 https://example.gov/a")

    user = "调研扬州最新购房政策"
    text = await compose_workforce_answer(
        user,
        subtasks=[{"id": "task_1", "result": "Subtask completed."}],
        messages=_research_ok_messages(user, "薄"),
        llm=Cap(),
    )
    assert called
    assert "合成后" in text


def test_best_user_facing_ignores_prior_turn_article():
    from app.runtime.v2.synthesize import best_user_facing_text, evidence_blob

    prior = (
        "算法备案审核时长通常为二十个工作日。"
        "材料包括算法安全自评估报告、拟公示内容等。"
    ) * 8
    current = "请示已写好，路径见工作区。"
    msgs = [
        HumanMessage(content="算法备案审核时长"),
        ToolMessage(
            content="URL: https://old.example/beian\n\nPAGE_OLD_BEIAN_BODY",
            tool_call_id="old",
            name="web_fetch",
        ),
        AIMessage(content=prior),
        HumanMessage(content="#official-document-writing 写一份关于增加项目经费的请示"),
        AIMessage(content=current),
        AIMessage(content="missing file: /tmp/\\u5173\\u4e8e请示.docx\nparaId 001"),
    ]
    best = best_user_facing_text(msgs)
    assert "算法备案" not in best
    assert "请示已写好" in best
    blob = evidence_blob(msgs)
    assert "PAGE_OLD_BEIAN_BODY" not in blob
    assert "算法备案" not in blob


def test_critic_does_not_reuse_prior_research_for_new_question():
    old = "调研扬州最新购房政策"
    new = "调研杭州最新购房政策"
    msgs = _research_ok_messages(old, "扬州限购已放宽。")
    msgs.extend(
        [
            HumanMessage(content=new),
            AIMessage(content="杭州也放宽了。来源 https://example.gov/a"),
        ]
    )
    v = heuristic_critic(new, msgs)
    assert v.next == "act"
    assert any("web_search" in m for m in v.missing)


def test_critic_followup_expand_still_passes():
    v = heuristic_critic(
        "把刚才第三点展开",
        [
            HumanMessage(content="写三点合作建议"),
            AIMessage(content="1. 对等持股 2. 数据隔离 3. 退出条款"),
            HumanMessage(content="把刚才第三点展开"),
            AIMessage(
                content="第三点退出条款应写清触发条件、对赌期、回购定价与争议解决，避免口头约定。"
            ),
        ],
    )
    assert v.next == "answer"


def test_decode_unicode_office_path():
    from app.runtime.v2.office import decode_fs_path, paths_from_text, validate_office_file

    escaped = "/Users/foo/AIS/\\u5173\\u4e8e增加项目经费的请示.docx"
    assert decode_fs_path(escaped).endswith("关于增加项目经费的请示.docx")
    found = paths_from_text("Wrote " + escaped)
    assert found
    assert "关于" in found[0]
    assert "\\u" not in found[0]
    ok, msg = validate_office_file("/tmp/\\u5173\\u4e8e请示.docx")
    assert ok is False
    assert "关于请示.docx" in msg
    assert "\\u5173" not in msg
