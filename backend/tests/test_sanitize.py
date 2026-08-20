"""Regression tests for tool-response sanitization (OpenAI 400 round-trip bug)."""

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool as langchain_tool

from app.agents.factory import create_single_agent
from app.agents.sanitize import ensure_tool_responses, prepare_model_messages, strip_model_junk
from app.graphs.single_agent import compile_single_agent_graph
from app.graphs.state import WorkforceState


def _ids_answered_by(messages) -> set[str]:
    """Return tool_call ids that have a following ToolMessage response."""
    answered: set[str] = set()
    for i, m in enumerate(messages):
        if not isinstance(m, AIMessage):
            continue
        calls = list(getattr(m, "tool_calls", None) or [])
        invalid = list(getattr(m, "invalid_tool_calls", None) or [])
        ids = {c["id"] for c in calls} | {c["id"] for c in invalid if c.get("id")}
        following = {
            nxt.tool_call_id
            for nxt in messages[i + 1 :]
            if isinstance(nxt, ToolMessage)
        }
        answered |= ids & following
    return answered


class TestEnsureToolResponses:
    def test_invalid_tool_calls_get_synthetic_response(self):
        """DeepSeek-style malformed args must not leave an unanswered call."""
        messages = [
            HumanMessage(content="do it"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "list_skills",
                        "args": {},
                        "id": "call_ok",
                        "type": "tool_call",
                    }
                ],
                invalid_tool_calls=[
                    {
                        "name": "load_skill",
                        "args": '{"name": officecli}',
                        "id": "call_bad",
                        "error": None,
                    }
                ],
            ),
            ToolMessage(
                content="[...]",
                tool_call_id="call_ok",
                name="list_skills",
            ),
        ]
        sanitized = ensure_tool_responses(messages)
        # Both the real and the synthetic invalid-call responses must be present.
        tool_ids = {
            m.tool_call_id for m in sanitized if isinstance(m, ToolMessage)
        }
        assert tool_ids == {"call_ok", "call_bad"}
        # The synthetic response tells the model to fix the arguments.
        bad = next(
            m for m in sanitized if isinstance(m, ToolMessage) and m.tool_call_id == "call_bad"
        )
        assert "Fix the arguments" in bad.content
        # Invariant holds: every assistant call id has a following tool response.
        all_ids = {
            c["id"]
            for m in sanitized
            if isinstance(m, AIMessage)
            for c in list(getattr(m, "tool_calls", None) or [])
            + list(getattr(m, "invalid_tool_calls", None) or [])
            if c.get("id")
        }
        assert all_ids <= _ids_answered_by(sanitized)

    def test_interrupted_checkpoint_gets_retry_response(self):
        """An assistant tool_calls message with no tool responses is patched."""
        messages = [
            SystemMessage(content="You are the agent."),
            HumanMessage(content="do it"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "fs.write",
                        "args": {"path": "x", "content": "y"},
                        "id": "call_1",
                        "type": "tool_call",
                    }
                ],
            ),
        ]
        sanitized = ensure_tool_responses(messages)
        tool_ids = {
            m.tool_call_id for m in sanitized if isinstance(m, ToolMessage)
        }
        assert tool_ids == {"call_1"}
        assert "not executed" in next(
            m.content for m in sanitized if isinstance(m, ToolMessage)
        )

    def test_complete_history_is_unchanged(self):
        messages = [
            HumanMessage(content="do it"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "mock_tool",
                        "args": {"query": "hi"},
                        "id": "call_ok",
                        "type": "tool_call",
                    }
                ],
            ),
            ToolMessage(content="result", tool_call_id="call_ok", name="mock_tool"),
            AIMessage(content="done"),
        ]
        sanitized = ensure_tool_responses(messages)
        assert sanitized == messages

    def test_production_invalid_call_after_answered_call(self):
        """Real checkpoint shape: valid call answered, invalid call orphaned."""
        messages = [
            HumanMessage(content="帮我做一份财务模型"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "list_skills",
                        "args": {},
                        "id": "call_00_ok",
                        "type": "tool_call",
                    }
                ],
                invalid_tool_calls=[
                    {
                        "type": "invalid_tool_call",
                        "id": "call_01_bad",
                        "name": "load_skill",
                        "args": '{"name": officecli-financial-model}',
                        "error": None,
                    }
                ],
            ),
            ToolMessage(
                content="[skills]", tool_call_id="call_00_ok", name="list_skills"
            ),
        ]
        sanitized = ensure_tool_responses(messages)
        tool_ids = {
            m.tool_call_id for m in sanitized if isinstance(m, ToolMessage)
        }
        assert tool_ids == {"call_00_ok", "call_01_bad"}
        assert all_ids_in(sanitized) <= _ids_answered_by(sanitized)

    def test_idless_tool_call_gets_repaired_id_and_response(self):
        """A tool call without id must get a generated id + synthetic response."""
        messages = [
            HumanMessage(content="do it"),
            AIMessage(
                content="",
                tool_calls=[{"name": "mock_tool", "args": {}, "id": None, "type": "tool_call"}],
            ),
        ]
        sanitized = ensure_tool_responses(messages)
        ai = next(m for m in sanitized if isinstance(m, AIMessage))
        assert len(ai.tool_calls) == 1
        new_id = ai.tool_calls[0]["id"]
        assert new_id
        tool_ids = {m.tool_call_id for m in sanitized if isinstance(m, ToolMessage)}
        assert tool_ids == {new_id}
        # Original message must not be mutated in place.
        assert not (messages[1].tool_calls[0].get("id") or "")

    def test_dict_form_assistant_message_is_patched(self):
        """Serialized dict messages (role/tool_call_id form) are also covered."""
        messages = [
            {"role": "user", "content": "do it"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_dict_1",
                        "type": "function",
                        "function": {"name": "mock_tool", "arguments": "{}"},
                        "name": "mock_tool",
                    }
                ],
            },
        ]
        sanitized = ensure_tool_responses(messages)
        tool_ids = {
            m.tool_call_id for m in sanitized if isinstance(m, ToolMessage)
        }
        assert tool_ids == {"call_dict_1"}
        # A dict tool response already present counts as answered.
        messages2 = list(messages) + [
            {"role": "tool", "tool_call_id": "call_dict_1", "content": "ok"}
        ]
        sanitized2 = ensure_tool_responses(messages2)
        assert not any(isinstance(m, ToolMessage) for m in sanitized2)


def all_ids_in(messages) -> set[str]:
    return {
        c["id"]
        for m in messages
        if isinstance(m, AIMessage)
        for c in list(getattr(m, "tool_calls", None) or [])
        + list(getattr(m, "invalid_tool_calls", None) or [])
        if c.get("id")
    }


class OpenAIValidatorModel(BaseChatModel):
    """Mimics OpenAI validation: 400 when an assistant tool_calls id is unanswered."""

    responses: list = []
    idx: int = 0

    def bind_tools(self, tools, **kwargs):
        return self

    def _check(self, messages):
        for i, m in enumerate(messages):
            if not isinstance(m, AIMessage):
                continue
            calls = list(getattr(m, "tool_calls", None) or [])
            invalid = list(getattr(m, "invalid_tool_calls", None) or [])
            ids = {c["id"] for c in calls} | {
                c["id"] for c in invalid if c.get("id")
            }
            following = {
                nxt.tool_call_id
                for nxt in messages[i + 1 :]
                if isinstance(nxt, ToolMessage)
            }
            missing = ids - following
            if missing:
                raise RuntimeError(
                    "400 invalid_request_error: An assistant message with 'tool_calls' "
                    "must be followed by tool messages responding to each "
                    f"'tool_call_id'. missing={missing}"
                )

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self._check(list(messages))
        if self.idx >= len(self.responses):
            raise RuntimeError("FakeChatModel exhausted its scripted responses")
        message = self.responses[self.idx]
        self.idx += 1
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._generate(messages, stop, run_manager, **kwargs)

    @property
    def _llm_type(self) -> str:
        return "openai-validator"


@langchain_tool
def _mock_tool(query: str) -> str:
    """A mock tool for agent tests."""
    return f"mock:{query}"


class TestAgentRoundTrip:
    @pytest.mark.asyncio
    async def test_invalid_tool_call_does_not_400(self):
        """Single agent with a malformed tool call must still complete."""
        model = OpenAIValidatorModel(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "mock_tool",
                            "args": {"query": "hi"},
                            "id": "call_ok",
                            "type": "tool_call",
                        }
                    ],
                    invalid_tool_calls=[
                        {
                            "name": "load_skill",
                            "args": '{"name": officecli}',
                            "id": "call_bad",
                            "error": None,
                        }
                    ],
                ),
                AIMessage(content="done"),
            ]
        )
        agent = create_single_agent(
            system_prompt="You are the Single Agent.",
            model=model,
            tools=[_mock_tool],
        )
        graph = compile_single_agent_graph(agent)
        result = await graph.ainvoke(
            WorkforceState(
                messages=[HumanMessage(content="do the thing")],
                task_id="sa-sanitize",
                session_mode="single-agent",
                user_text="do the thing",
                round=0,
            )
        )
        texts = " ".join(
            str(m.content) for m in result["messages"] if m.content
        )
        assert "done" in texts


class TestPrepareModelMessages:
    def test_merges_leading_systems(self):
        out = prepare_model_messages(
            [
                SystemMessage(content="role A"),
                SystemMessage(content="rules B"),
                HumanMessage(content="调研扬州"),
            ]
        )
        assert len(out) == 2
        assert isinstance(out[0], SystemMessage)
        assert "role A" in out[0].content
        assert "rules B" in out[0].content
        assert isinstance(out[1], HumanMessage)

    def test_mid_thread_system_is_folded_into_tool_result(self):
        out = prepare_model_messages(
            [
                SystemMessage(content="agent"),
                HumanMessage(content="q"),
                AIMessage(
                    content=" ",
                    tool_calls=[
                        {
                            "id": "c1",
                            "name": "load_skill",
                            "args": {"name": "x"},
                            "type": "tool_call",
                        }
                    ],
                ),
                ToolMessage(content="skill body", tool_call_id="c1", name="load_skill"),
                SystemMessage(content="<loaded_skill>body</loaded_skill>"),
            ]
        )
        roles = [getattr(m, "type", None) for m in out]
        assert roles.count("system") == 1
        assert "human" not in roles[2:]
        assert isinstance(out[-1], ToolMessage)
        assert "skill body" in str(out[-1].content)
        assert "loaded_skill" in str(out[-1].content)

    def test_instruction_between_parallel_tools_is_folded(self):
        out = prepare_model_messages(
            [
                HumanMessage(content="写一份请示"),
                AIMessage(
                    content="加载公文写作规范和 Word 文档生成技能。",
                    tool_calls=[
                        {
                            "id": "c1",
                            "name": "load_skill",
                            "args": {"name": "official-document-writing"},
                            "type": "tool_call",
                        },
                        {
                            "id": "c2",
                            "name": "load_skill",
                            "args": {"name": "officecli-docx"},
                            "type": "tool_call",
                        },
                    ],
                ),
                ToolMessage(content="公文规范", tool_call_id="c1", name="load_skill"),
                HumanMessage(content="[Instruction]\n<loaded_skill>公文规范</loaded_skill>"),
                ToolMessage(content="Word 技能", tool_call_id="c2", name="load_skill"),
                HumanMessage(content="[Instruction]\n<loaded_skill>Word 技能</loaded_skill>"),
            ]
        )
        roles = [getattr(m, "type", None) for m in out]
        assert roles == ["human", "ai", "tool", "tool"]
        assert "loaded_skill" in str(out[2].content)
        assert "loaded_skill" in str(out[3].content)

    def test_empty_tool_call_content_becomes_space(self):
        out = prepare_model_messages(
            [
                HumanMessage(content="q"),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "c1",
                            "name": "web_search",
                            "args": {"query": "扬州"},
                            "type": "tool_call",
                        }
                    ],
                ),
            ]
        )
        assert out[-1].content == " "


def test_strip_model_junk_minimax_tokens():
    raw = (
        "大模型备案分算法备案与生成式服务备案两步。\n"
        "]<|minimax|>[0xf\n"
        "]<|minimax|>[0xf\n"
        "]<|minimax|>[0xX\n"
        "详见官方指引。"
    )
    cleaned = strip_model_junk(raw)
    assert "<|minimax|>" not in cleaned
    assert "0xf" not in cleaned
    assert "算法备案" in cleaned
    assert "官方指引" in cleaned
    assert strip_model_junk("]<|minimax|>[0xf") == ""
    assert strip_model_junk("] <|minimax|> [0xX") == ""
