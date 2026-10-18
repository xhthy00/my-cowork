"""Exercise the real DeepSeek SDK and official graph against an HTTP protocol stub."""
import asyncio
import json

import httpx
import pytest
from langchain_openai import ChatOpenAI

from cowork_harness.models import planning_model
from cowork_harness.service import RuntimeService
from model_integrations.openai_compat import create_openai_compat
from runtime_contract import RunRequest, ToolSpec


@pytest.mark.parametrize('streaming', [False, True])
@pytest.mark.asyncio
async def test_native_deepseek_plans_without_thinking_then_restores_and_echoes_reasoning(tmp_path, streaming):
    requests = []
    tool_responses = [
        ('write_todos', {'todos': [{'content': '检索并回答', 'status': 'in_progress'}]}),
        ('lookup', {}),
        ('write_todos', {'todos': [{'content': '检索并回答', 'status': 'completed'}]}),
    ]
    async def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        index = len(requests) - 1
        forced = isinstance(body.get('tool_choice'), dict) or body.get('tool_choice') == 'required'
        thinking = body.get('thinking', {}).get('type', 'enabled') != 'disabled'
        if thinking and forced:
            return httpx.Response(400, json={'error': {'message': 'Thinking mode does not support this tool_choice',
                'type': 'invalid_request_error'}})
        if index == 0:
            assert not thinking
            assert body['tool_choice']['function']['name'] == 'write_todos'
            assert [tool['function']['name'] for tool in body['tools']] == ['write_todos']
        else:
            assert thinking and not forced
            assistant_turns = [message for message in body['messages'] if message['role'] == 'assistant']
            assert assistant_turns[0]['reasoning_content'] == ''
            for turn_index, message in enumerate(assistant_turns[1:], 1):
                assert message['reasoning_content'] == f'reason-{turn_index}'
            tools = {tool['function']['name'] for tool in body['tools']}
            assert 'lookup' in tools
            assert not {'task', 'write_file', 'edit_file', 'delete', 'execute'} & tools
        if index < 3:
            name, args = tool_responses[index]
            tool_calls = [{'id': f'call-{index}', 'type': 'function',
                'function': {'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}]
            message = {'role': 'assistant', 'content': None, 'tool_calls': tool_calls}
            finish_reason = 'tool_calls'
        else:
            message = {'role': 'assistant', 'content': '检索结果已核实'}
            finish_reason = 'stop'
        if thinking:
            message['reasoning_content'] = f'reason-{index}'
        envelope = {'id': f'reply-{index}', 'created': 1, 'model': 'deepseek-flash',
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}}
        if body.get('stream'):
            delta = {key: value for key, value in message.items() if value is not None}
            if 'tool_calls' in delta:
                delta['tool_calls'] = [{**call, 'index': i} for i, call in enumerate(delta['tool_calls'])]
            chunk = {**envelope, 'object': 'chat.completion.chunk',
                'choices': [{'index': 0, 'delta': delta, 'finish_reason': finish_reason}]}
            return httpx.Response(200, headers={'Content-Type': 'text/event-stream'},
                content='data: ' + json.dumps(chunk, ensure_ascii=False) + '\n\ndata: [DONE]\n\n')
        return httpx.Response(200, json={**envelope, 'object': 'chat.completion',
            'choices': [{'index': 0, 'message': message, 'finish_reason': finish_reason}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        model = create_openai_compat('deepseek-flash', 'test-key', base_url='https://api.deepseek.com')
        # Recreate with the public client field; all requests remain in MockTransport.
        model = type(model)(model='deepseek-flash', api_key='test-key', base_url='https://api.deepseek.com',
            extra_body=model.extra_body, http_async_client=client, disable_streaming=not streaming, max_retries=0)
        async def host(op, *args, **kwargs):
            return {'decision': 'allow', 'ticket': 'ticket'} if op == 'authorize' else '材料已核实'
        service = RuntimeService(tmp_path, model_factory=lambda _: model, call_host=host)
        await service.start()
        try:
            await service.submit(RunRequest(task_id='native', session_id='chat', text='检索材料并回答',
                scope_ref='scope', workspace=str(tmp_path), mode='single-agent', models={'supervisor': {'model': 'test'}},
                tools=[ToolSpec(name='lookup', description='检索材料', input_schema={'type': 'object', 'properties': {}})]))
            await asyncio.wait_for(service.tasks['native'], 5)
            events = service.store.events('native')
            assert events[-1]['status'] == 'ok', events[-1]
            assert len(requests) == 4
            assert model.extra_body == {'thinking': {'type': 'enabled'}}
            assert next(event for event in events if event['type'] == 'todo_state' and event['todos'])['seq'] < next(
                event for event in events if event['type'] == 'tool.start' and event['tool'] == 'lookup')['seq']
            assert 'reason-' not in ''.join(event['delta'] for event in events if event['type'] == 'step.delta')
        finally:
            await service.close()


def test_auto_planning_keeps_unknown_endpoint_configuration():
    original = ChatOpenAI(model='deepseek-local', api_key='test-key', base_url='http://localhost:8000/v1',
        extra_body={'chat_template_kwargs': {'thinking': True, 'enable_thinking': True, 'keep': 'yes'},
                    'enable_thinking': True, 'other': {'preserve': True}})
    planner = planning_model(original)
    assert planner.extra_body['enable_thinking'] is True
    assert planner.extra_body['chat_template_kwargs'] == {'thinking': True, 'enable_thinking': True, 'keep': 'yes'}
    assert planner.extra_body['other'] == {'preserve': True}
    assert original.extra_body['enable_thinking'] is True
    assert original.extra_body['chat_template_kwargs']['thinking'] is True


def test_native_planning_disables_server_default_and_removes_effort():
    original = ChatOpenAI(model='deepseek-flash', api_key='test-key', base_url='https://api.deepseek.com',
        reasoning_effort='high', extra_body={'reasoning_effort': 'high', 'custom': 'preserved'})
    planner = planning_model(original)
    assert planner.extra_body == {'thinking': {'type': 'disabled'}, 'custom': 'preserved'}
    assert planner.reasoning_effort is None
    assert original.reasoning_effort == 'high'


def test_mixed_fallback_keeps_deepseek_history_out_of_other_provider_requests():
    from cowork_harness.models import deepseek_history_model
    from langchain_core.messages import AIMessage
    from model_integrations.anthropic import create_anthropic
    from model_integrations.fallback import FallbackChatModel
    native = create_openai_compat('deepseek-flash', 'test-key', base_url='https://api.deepseek.com')
    other = create_anthropic('claude-sonnet-4-5', 'test-key')
    chain = FallbackChatModel([native, other])
    adapted = deepseek_history_model(chain, [AIMessage(content='answer', additional_kwargs={'reasoning_content': 'thought'})])
    assert adapted.models[0].extra_body['messages'][0]['reasoning_content'] == 'thought'
    assert adapted.models[1] is other
    assert 'messages' not in native.extra_body
