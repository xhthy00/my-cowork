from app.llm.model_config import ModelConfig
from app.llm.reasoning import reasoning_kwargs
import json
import httpx
import pytest


def options(mode, **kwargs):
    return reasoning_kwargs(ModelConfig(id="a", model="alias", provider="openai_compat", api_key="test", reasoning_mode=mode, **kwargs))


def test_vendor_wire_parameters_are_distinct():
    assert options("deepseek", thinking_enabled=True, reasoning_effort="high") == {"extra_body": {"thinking": {"type": "enabled"}, "reasoning_effort": "high"}}
    assert options("moonshot", reasoning_effort="max") == {"extra_body": {"thinking": {"type": "enabled", "effort": "max"}}}
    assert options("qwen", thinking_enabled=False) == {"extra_body": {"enable_thinking": False}}
    assert options("openrouter", reasoning_effort="high") == {"extra_body": {"reasoning": {"effort": "high"}}}


def test_default_sends_no_unsolicited_reasoning_parameters():
    assert options("default") == {}
    assert options("anthropic") == {}


def test_anthropic_manual_and_adaptive_options():
    assert options("anthropic", thinking_budget=4096) == {"thinking": {"type": "enabled", "budget_tokens": 4096}}
    assert options("anthropic", reasoning_effort="high", thinking_enabled=True) == {"thinking": {"type": "adaptive"}, "output_config": {"effort": "high"}}


def test_reasoning_survives_stream_tool_roundtrip_but_not_model_switch():
    from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage
    from app.llm.providers.reasoning_openai import ReasoningChatOpenAI
    client = ReasoningChatOpenAI(model="kimi", api_key="test", base_url="https://example.org/v1")
    first = client._convert_chunk_to_generation_chunk({"choices": [{"delta": {"role": "assistant", "reasoning_content": "think "}}]}, AIMessageChunk, None)
    second = client._convert_chunk_to_generation_chunk({"choices": [{"delta": {"reasoning_content": "more", "tool_calls": [{"index": 0, "id": "call", "type": "function", "function": {"name": "read", "arguments": "{}"}}]}}]}, AIMessageChunk, None)
    reply = (first + second).message
    messages = [HumanMessage("hi"), reply, ToolMessage("result", tool_call_id="call")]
    assert client._get_request_payload(messages)["messages"][1]["reasoning_content"] == "think more"
    other = ReasoningChatOpenAI(model="other", api_key="test", base_url="https://example.org/v1")
    assert "reasoning_content" not in other._get_request_payload(messages)["messages"][1]


def test_native_signed_blocks_survive_runtime_but_are_removed_after_model_switch():
    from langchain_core.messages import AIMessageChunk
    from app.runtime.v2.loop import _as_ai_message, _stamp_model
    from app.agents.sanitize import prepare_model_messages
    from app.llm.model_config import model_scope
    blocks = [{"type": "thinking", "thinking": "private", "signature": "sig"}, {"type": "text", "text": "answer"}]
    a = ModelConfig(id="a", provider="anthropic", model="a", api_key="test")
    b = ModelConfig(id="b", provider="anthropic", model="b", api_key="test")
    with model_scope(a):
        message = _stamp_model(_as_ai_message(AIMessageChunk(content=blocks), ["answer"]))
        assert prepare_model_messages([message])[0].content == blocks
    with model_scope(b):
        assert prepare_model_messages([message])[0].content == [{"type": "text", "text": "answer"}]
    assert message.content == blocks


def test_responses_transport_is_selected_even_at_default_effort():
    assert options("openai-responses") == {"use_responses_api": True}
    assert options("minimax", thinking_enabled=True) == {"extra_body": {"thinking": {"type": "adaptive"}}}


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["deepseek", "moonshot", "qwen", "openrouter", "google", "minimax"])
async def test_real_sdk_stream_and_tool_continuation_wire_payload(mode):
    from langchain_core.messages import HumanMessage, ToolMessage
    from app.llm.providers.reasoning_openai import ReasoningChatOpenAI

    requests = []
    def transport(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if payload.get("stream"):
            chunks = [
                {"role": "assistant", "reasoning_content": "preserved reasoning"},
                {"tool_calls": [{"index": 0, "id": "call_1", "type": "function", "function": {"name": "read", "arguments": "{}"}}]},
            ]
            body = "".join("data: " + json.dumps({"id": "chatcmpl-test", "object": "chat.completion.chunk", "created": 1, "model": "alias", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}) + "\n\n" for delta in chunks)
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=body + "data: [DONE]\n\n")
        return httpx.Response(200, json={"id": "chatcmpl-test", "object": "chat.completion", "created": 1, "model": "alias", "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 20, "completion_tokens": 3, "total_tokens": 23}})

    kwargs = options(mode, reasoning_effort="high")
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        llm = ReasoningChatOpenAI(model="alias", api_key="test", base_url="https://mock.invalid/v1", http_async_client=http, **kwargs)
        bound = llm.bind_tools([{"type": "function", "function": {"name": "read", "parameters": {"type": "object", "properties": {}}}}])
        reply = None
        async for chunk in bound.astream([HumanMessage("read file")]):
            reply = chunk if reply is None else reply + chunk
        await bound.ainvoke([HumanMessage("read file"), reply, ToolMessage("file contents", tool_call_id="call_1")])
    assert len(requests) == 2
    for payload in requests:
        assert payload["model"] == "alias"
        for key, value in kwargs.get("extra_body", {}).items():
            assert payload[key] == value
        if "reasoning_effort" in kwargs:
            assert payload["reasoning_effort"] == "high"
    assert requests[1]["messages"][1]["reasoning_content"] == "preserved reasoning"
    assert requests[1]["messages"][2]["tool_call_id"] == "call_1"


@pytest.mark.asyncio
async def test_openai_responses_and_anthropic_native_sdk_requests(monkeypatch):
    from langchain_openai import ChatOpenAI
    from langchain_anthropic import ChatAnthropic
    requests = []
    def transport(request):
        requests.append((request.url.path, json.loads(request.content)))
        if request.url.path.endswith("/responses"):
            return httpx.Response(200, json={"id": "resp_test", "object": "response", "created_at": 1, "status": "completed", "model": "alias", "output": [{"type": "message", "id": "msg_test", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": "ok", "annotations": []}]}]})
        return httpx.Response(200, json={"id": "msg_test", "type": "message", "role": "assistant", "model": "alias", "content": [{"type": "thinking", "thinking": "private", "signature": "sig"}, {"type": "text", "text": "ok"}], "stop_reason": "end_turn", "usage": {"input_tokens": 10, "output_tokens": 3}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        openai = ChatOpenAI(model="alias", api_key="test", base_url="https://mock.invalid/v1", http_async_client=http, **options("openai-responses", reasoning_effort="high"))
        await openai.ainvoke("hi")
        monkeypatch.setattr("langchain_anthropic.chat_models._get_default_async_httpx_client", lambda **_: http)
        anthropic = ChatAnthropic(model="alias", api_key="test", base_url="https://mock.invalid", max_tokens=4096, **options("anthropic", reasoning_effort="high", thinking_enabled=True))
        await anthropic.ainvoke("hi")
    assert requests[0][0] == "/v1/responses"
    assert requests[0][1]["reasoning"]["effort"] == "high"
    assert requests[1][1]["thinking"] == {"type": "adaptive"}
    assert requests[1][1]["output_config"] == {"effort": "high"}


def test_anthropic_effort_does_not_enable_thinking_implicitly():
    assert options("anthropic", reasoning_effort="high") == {"output_config": {"effort": "high"}}
    config = ModelConfig(id="a", provider="anthropic", model="claude-opus-4-5", api_key="test", reasoning_mode="anthropic", allowed_efforts=("low", "high"), allow_thinking_toggle=True)
    selected = config.with_reasoning({"enabled": False, "effort": "high"})
    assert reasoning_kwargs(selected) == {"thinking": {"type": "disabled"}, "output_config": {"effort": "high"}}
