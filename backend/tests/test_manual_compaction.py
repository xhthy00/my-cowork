import pytest
from langchain_core.messages import AIMessage, HumanMessage
from app.runtime.v2.compact import compact_session_history


@pytest.mark.asyncio
async def test_custom_compaction_includes_early_long_tail_and_already_compacted_content():
    seen = []
    class Model:
        async def ainvoke(self, messages):
            seen.append(str(messages))
            return AIMessage(content="摘要：保留项目目标、早期事实和未完成事项。")
    canonical = [HumanMessage("early-needle " + "x" * 60000 + " long-tail-needle"), AIMessage("answer"), HumanMessage("recent"), AIMessage("latest")]
    old = {"boundary_index": 2, "summary_text": "already compacted " * 100}
    visible, state = await compact_session_history(canonical, old, llm=Model(), threshold=2000, force=True, focus="保留 needle")
    text = "\n".join(seen)
    assert "early-needle" in text and "long-tail-needle" in text and "保留 needle" in text
    assert state is not old
    assert canonical[0].content.endswith("long-tail-needle")


@pytest.mark.asyncio
async def test_failure_does_not_replace_old_snapshot_with_mechanical_fallback():
    class Broken:
        async def ainvoke(self, messages):
            raise RuntimeError("offline")
    canonical = [HumanMessage("old" * 10000), AIMessage("answer"), HumanMessage("recent"), AIMessage("latest")]
    old = {"boundary_index": 2, "summary_text": "previous"}
    with pytest.raises(ValueError, match="压缩"):
        await compact_session_history(canonical, old, llm=Broken(), force=True, focus="保留计划")
    assert old == {"boundary_index": 2, "summary_text": "previous"}


@pytest.mark.asyncio
async def test_compaction_cannot_commit_view_that_still_exceeds_target():
    canonical = [HumanMessage("old " * 10000), AIMessage("answer"), HumanMessage("recent " * 4000), AIMessage("latest")]
    async def summarize(messages):
        return "short summary"
    with pytest.raises(ValueError, match="压缩"):
        await compact_session_history(canonical, threshold=2048, summarize=summarize, force=True)
    with pytest.raises(ValueError, match="压缩"):
        await compact_session_history(canonical, threshold=2048, summarize=summarize)


@pytest.mark.asyncio
async def test_compaction_accepts_text_blocks_without_exposing_private_thinking():
    class Model:
        async def ainvoke(self, messages):
            return AIMessage(content=[{"type": "thinking", "thinking": "private"}, {"type": "text", "text": "简洁摘要"}])
    canonical = [HumanMessage("old " * 10000), AIMessage("answer"), HumanMessage("recent"), AIMessage("latest")]
    visible, state = await compact_session_history(canonical, llm=Model(), threshold=2048, force=True)
    assert state and "简洁摘要" in state["summary_text"]
    assert "private" not in state["summary_text"]


@pytest.mark.asyncio
async def test_larger_budget_restores_original_and_smaller_reuses_snapshot():
    from app.runtime.v2.compact import session_view
    from app.llm.model_config import ModelConfig, model_scope
    canonical = [HumanMessage("early detail " * 2500), AIMessage("answer"), HumanMessage("recent"), AIMessage("latest")]
    small = ModelConfig(id="small", provider="openai_compat", model="small", api_key="fake", context_window=5000, output_limit=1000)
    big = ModelConfig(id="big", provider="openai_compat", model="big", api_key="fake", context_window=50000, output_limit=1000)
    async def summarize(messages):
        return "brief summary"
    with model_scope(small):
        compacted, state = await compact_session_history(canonical, summarize=summarize)
        assert state and state["input_budget"] == small.input_budget
    with model_scope(big):
        visible, effective = await compact_session_history(canonical, state)
        assert visible == canonical and effective is None
        assert session_view(canonical, state) == canonical
    with model_scope(small):
        visible, effective = await compact_session_history(canonical, state)
        assert visible == compacted and effective == state


@pytest.mark.asyncio
async def test_larger_budget_rebuilds_from_original_when_all_still_does_not_fit():
    from app.llm.model_config import ModelConfig, model_scope
    canonical = [HumanMessage("early-needle " * 10000), AIMessage("answer"), HumanMessage("recent"), AIMessage("latest")]
    old = {"boundary_index": 2, "summary_text": "tiny old summary", "input_budget": 2000}
    seen = []
    async def summarize(messages):
        seen.extend(messages)
        return "recovered detail"
    with model_scope(ModelConfig(id="big", provider="openai_compat", model="big", api_key="fake", context_window=12000, output_limit=1000)):
        visible, state = await compact_session_history(canonical, old, summarize=summarize)
    assert any("early-needle" in m.content for m in seen)
    assert state["input_budget"] > old["input_budget"]
    assert "recovered detail" in visible[0].content
    assert old["summary_text"] == "tiny old summary"


@pytest.mark.asyncio
async def test_automatic_failure_stops_instead_of_sending_old_oversized_history():
    canonical = [HumanMessage("old " * 10000), AIMessage("answer"), HumanMessage("recent")]
    class Broken:
        async def ainvoke(self, messages):
            raise RuntimeError("offline")
    with pytest.raises(ValueError, match="压缩失败"):
        await compact_session_history(canonical, llm=Broken(), threshold=2048)
    assert len(canonical) == 3


@pytest.mark.asyncio
async def test_700k_conversation_switches_1m_to_300k_and_back_without_losing_original():
    from app.llm.model_config import ModelConfig, model_scope
    from app.llm.token_counter import count_tokens
    canonical = [HumanMessage("detail " * 350000), AIMessage("evidence " * 350000), HumanMessage("继续"), AIMessage("latest")]
    assert 700000 <= count_tokens(canonical) < 701000
    big = ModelConfig(id="big", provider="openai_compat", model="big", api_key="fake", context_window=1000000)
    small = ModelConfig(id="small", provider="openai_compat", model="small", api_key="fake", context_window=300000)
    async def summarize(messages):
        assert messages == canonical[:2]
        return "保留目标、证据和后续事项"
    with model_scope(big):
        view, state = await compact_session_history(canonical)
        assert view == canonical and state is None
    with model_scope(small):
        view, state = await compact_session_history(canonical, summarize=summarize)
        assert count_tokens(view) < small.compression_trigger
    with model_scope(big):
        view, _ = await compact_session_history(canonical, state)
        assert view == canonical
