"""Real SDK/graph protocol regressions; no vendor credentials or network calls."""
import asyncio
import json

import httpx
import openrouter
import pytest
from langchain_openrouter import ChatOpenRouter

from cowork_harness.service import RuntimeService
from model_integrations.openai_compat import create_openai_compat, endpoint_family
from runtime_contract import RunRequest, ToolSpec
from model_integrations.anthropic import create_anthropic
from model_integrations.fallback import FallbackChatModel


CASES = [
    ('deepseek-flash', 'https://api.deepseek.com/v1', 'write_todos'),
    ('gpt-4o-mini', 'https://api.openai.com/v1', 'write_todos'),
    ('gpt-5-mini', 'https://api.openai.com/v1', 'write_todos'),
    ('kimi-k2.5', 'https://api.moonshot.ai/v1', 'required'),
    ('kimi-k2-turbo-preview', 'https://api.moonshot.cn/v1', 'required'),
    ('kimi-k2-thinking', 'https://api.moonshot.ai/v1', 'required'),
    ('glm-4.7', 'https://api.z.ai/api/paas/v4', 'auto'),
    ('glm-5.3', 'https://open.bigmodel.cn/api/paas/v4', 'auto'),
    ('qwen-plus', 'https://dashscope.aliyuncs.com/compatible-mode/v1', 'auto'),
    ('qwq-32b', 'https://dashscope.aliyuncs.com/compatible-mode/v1', 'auto'),
    ('MiniMax-M2.5', 'https://api.minimaxi.com/v1', 'auto'),
    ('MiniMax-M3', 'https://api.minimaxi.com/v1', 'auto'),
    ('MiniMax-M3.1-Flash-Preview', 'https://api.minimax.io/v1', 'auto'),
    ('qwen3:8b', 'http://localhost:11434/v1', 'auto'),
    ('glm-local', 'http://localhost:1234/v1', 'auto'),
    ('deepseek-local', 'http://localhost:8000/v1', 'auto'),
    ('anthropic/claude-sonnet-4-5', 'https://openrouter.ai/api/v1', 'auto'),
    ('deepseek/deepseek-flash', 'https://openrouter.ai/api/v1', 'auto'),
]


def completion(body, index, name, args=None, reasoning=None, details=None):
    message = {'role': 'assistant', 'content': '回答完成' if name is None else None}
    if name:
        message['tool_calls'] = [{'id': f'call-{index}', 'type': 'function',
            'function': {'name': name, 'arguments': json.dumps(args or {}, ensure_ascii=False)}}]
    if reasoning is not None:
        message['reasoning_content'] = reasoning
    if details is not None:
        message['reasoning'] = reasoning
        message['reasoning_details'] = details
    envelope = {'id': f'chatcmpl-{index}', 'created': 1, 'model': body['model'],
                'system_fingerprint': None,
                'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}}
    if body.get('stream'):
        if 'tool_calls' in message:
            message['tool_calls'] = [{**call, 'index': i} for i, call in enumerate(message['tool_calls'])]
        chunk = {**envelope, 'object': 'chat.completion.chunk',
            'choices': [{'index': 0, 'delta': message, 'finish_reason': 'tool_calls' if name else 'stop'}]}
        return httpx.Response(200, headers={'Content-Type': 'text/event-stream'},
            content='data: ' + json.dumps(chunk, ensure_ascii=False) + '\n\ndata: [DONE]\n\n')
    return httpx.Response(200, json={**envelope, 'object': 'chat.completion', 'choices': [
        {'index': 0, 'message': message, 'finish_reason': 'tool_calls' if name else 'stop', 'logprobs': None}]})


def with_transport(model, client, streaming):
    if isinstance(model, ChatOpenRouter):
        sdk = openrouter.OpenRouter(api_key='test-key', server_url=model.openrouter_api_base, async_client=client)
        return model.model_copy(update={'client': sdk, 'disable_streaming': not streaming, 'max_retries': 0})
    return type(model)(model=model.model_name, api_key='test-key',
        base_url=getattr(model, 'api_base', None) or model.openai_api_base,
        extra_body=model.extra_body, reasoning_effort=model.reasoning_effort,
        profile=model.profile, metadata=model.metadata, streaming=model.streaming, disable_streaming=not streaming and not model.streaming, http_async_client=client, max_retries=0)


@pytest.mark.parametrize('streaming', [False, True])
@pytest.mark.parametrize('model_name,base_url,choice', CASES, ids=[case[0] for case in CASES])
@pytest.mark.asyncio
async def test_provider_plan_tool_history_and_usage(tmp_path, model_name, base_url, choice, streaming):
    family = endpoint_family(base_url)
    requests = []
    opaque = [{'type': 'reasoning.encrypted', 'id': 'stable-id', 'index': 0,
               'format': 'anthropic-claude-v1', 'data': 'opaque-signature'}]

    async def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        index = len(requests) - 1
        selected = body.get('tool_choice')
        if index == 0:
            expected = {'type': 'function', 'function': {'name': 'write_todos'}} if choice == 'write_todos' else choice
            assert selected == expected
        else:
            assert selected in (None, 'auto')
        if index == 0:
            assert {tool['function']['name'] for tool in body['tools']} == (
                {'write_todos'} if choice == 'write_todos' else {'write_todos', 'ask_human'})
        else:
            tools = {tool['function']['name'] for tool in body['tools']}
            assert 'lookup' in tools and not {'task', 'execute', 'write_file', 'edit_file', 'delete'} & tools
        assert 'enable_thinking' not in body or family == 'qwen'
        assert 'chat_template_kwargs' not in body
        if family == 'moonshot' and model_name == 'kimi-k2.5':
            assert body['thinking'] == {'type': 'enabled'}
        if family == 'glm' and model_name == 'glm-4.7':
            assert body['thinking'] == {'type': 'enabled'}
        if model_name in ('kimi-k2-thinking', 'glm-5.3', 'MiniMax-M3.1-Flash-Preview'):
            assert body.get('thinking', {}).get('type') != 'disabled'
        if family == 'qwen':
            assert body['stream'] is True
        if family in ('custom', 'openrouter'):
            assert not any(key in body for key in ('enable_thinking', 'thinking', 'chat_template_kwargs', 'reasoning_effort'))
        if index == 2:
            previous = [m for m in body['messages'] if m['role'] == 'assistant'][-1]
            if family in ('moonshot', 'glm', 'minimax'):
                assert previous['reasoning_content'] == 'private-thought'
            if family == 'openrouter':
                assert previous['reasoning_details'][0]['data'] == 'opaque-signature'
        reasoning = 'private-thought' if family in ('moonshot', 'glm', 'minimax', 'openrouter', 'qwen') else None
        if index == 0:
            return completion(body, index, 'write_todos', {'todos': [{'content': '检索后答复', 'status': 'in_progress'}]}, reasoning)
        if index == 1:
            return completion(body, index, 'lookup', reasoning=reasoning, details=opaque if family == 'openrouter' else None)
        return completion(body, index, None, reasoning=reasoning)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        original = create_openai_compat(model_name, 'test-key', base_url=base_url)
        model = with_transport(original, client, streaming)
        async def host(op, *args, **kwargs):
            return {'decision': 'allow', 'ticket': 't'} if op == 'authorize' else '材料'
        service = RuntimeService(tmp_path, model_factory=lambda _: model, call_host=host)
        await service.start()
        try:
            await service.submit(RunRequest(task_id='matrix', session_id='chat', text='检索并答复', scope_ref='scope',
                workspace=str(tmp_path), mode='single-agent', models={'supervisor': {'model': model_name}},
                tools=[ToolSpec(name='lookup', description='检索', input_schema={'type': 'object', 'properties': {}})]))
            await asyncio.wait_for(service.tasks['matrix'], 5)
            events = service.store.events('matrix')
            assert events[-1]['status'] == 'ok', events[-1].get('error')
            assert len(requests) == 3
            budget = [event for event in events if event['type'] == 'budget.update'][-1]
            assert budget['tokens'] == 45 and budget['steps'] == 3
            from model_integrations.context import context_limit
            assert budget['context_limit'] == context_limit(original)
            assert budget['context_model'] == model_name
            assert budget['context_tokens'] == 10
            assert 'private-thought' not in ''.join(event['delta'] for event in events if event['type'] == 'step.delta')
        finally:
            await service.close()


@pytest.mark.parametrize('streaming', [False, True])
@pytest.mark.parametrize('model_name', ['claude-sonnet-4-20250514', 'claude-opus-4-6', 'claude-opus-5-5', 'claude-sonnet-5-5'])
@pytest.mark.asyncio
async def test_anthropic_thinking_signatures_and_custom_endpoint(tmp_path, monkeypatch, model_name, streaming):
    requests = []
    async def handler(request):
        assert request.url.host == 'anthropic.example.test'
        body = json.loads(request.content)
        requests.append(body)
        index = len(requests) - 1
        if index == 0 and '-5-5' not in model_name:
            assert 'thinking' not in body
            assert body['tool_choice'] == {'type': 'tool', 'name': 'write_todos'}
        else:
            assert body['thinking']['type'] == ('enabled' if model_name == 'claude-sonnet-4-20250514' else 'adaptive')
            assert body.get('tool_choice', {}).get('type', 'auto') == 'auto'
        if index == 2:
            previous = [m for m in body['messages'] if m['role'] == 'assistant'][-1]
            assert previous['content'][0]['signature'] == 'opaque-signature'
        content = []
        if 'thinking' in body:
            content.append({'type': 'thinking', 'thinking': '' if '-5-5' in model_name else 'private-thought', 'signature': 'opaque-signature'})
        if index < 2:
            content.append({'type': 'tool_use', 'id': f'call-{index}', 'name': 'write_todos' if index == 0 else 'lookup',
                'input': {'todos': [{'content': '检索后答复', 'status': 'in_progress'}]} if index == 0 else {}})
        else:
            content.append({'type': 'text', 'text': '回答完成'})
        reply = {'id': f'msg-{index}', 'type': 'message', 'role': 'assistant', 'model': model_name,
                 'content': content, 'stop_reason': 'tool_use' if index < 2 else 'end_turn',
                 'stop_sequence': None, 'usage': {'input_tokens': 10, 'output_tokens': 5}}
        if not body.get('stream'):
            return httpx.Response(200, json=reply)
        events = []
        def event(kind, **values):
            events.append('event: ' + kind + '\ndata: ' + json.dumps({'type': kind, **values}, ensure_ascii=False) + '\n\n')
        event('message_start', message={**reply, 'content': [], 'stop_reason': None, 'usage': {'input_tokens': 10, 'output_tokens': 0}})
        for block_index, block in enumerate(content):
            start = {**block}
            if block['type'] == 'tool_use':
                start['input'] = {}
                deltas = [{'type': 'input_json_delta', 'partial_json': json.dumps(block['input'], ensure_ascii=False)}]
            elif block['type'] == 'thinking':
                start.update(thinking='', signature='')
                deltas = [{'type': 'thinking_delta', 'thinking': block['thinking']},
                          {'type': 'signature_delta', 'signature': block['signature']}]
            else:
                start['text'] = ''
                deltas = [{'type': 'text_delta', 'text': block['text']}]
            event('content_block_start', index=block_index, content_block=start)
            for delta in deltas:
                event('content_block_delta', index=block_index, delta=delta)
            event('content_block_stop', index=block_index)
        event('message_delta', delta={'stop_reason': reply['stop_reason'], 'stop_sequence': None}, usage={'output_tokens': 5})
        event('message_stop')
        return httpx.Response(200, headers={'Content-Type': 'text/event-stream'}, content=''.join(events))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        # ChatAnthropic builds its SDK client lazily; replace only its test transport.
        import langchain_anthropic.chat_models as anthropic_models
        monkeypatch.setattr(anthropic_models, '_get_default_async_httpx_client', lambda **kwargs: client)
        original = create_anthropic(model_name, 'test-key', base_url='https://anthropic.example.test')
        model = type(original)(model=model_name, api_key='test-key', base_url=original.anthropic_api_url,
            thinking=original.thinking, max_tokens=original.max_tokens, disable_streaming=not streaming, max_retries=0)
        async def host(op, *args, **kwargs):
            return {'decision': 'allow', 'ticket': 't'} if op == 'authorize' else '材料'
        service = RuntimeService(tmp_path, model_factory=lambda _: model, call_host=host)
        await service.start()
        try:
            await service.submit(RunRequest(task_id='claude', session_id='chat', text='检索并答复', scope_ref='scope',
                workspace=str(tmp_path), mode='single-agent', models={'supervisor': {'model': model_name}},
                tools=[ToolSpec(name='lookup', description='检索', input_schema={'type': 'object', 'properties': {}})]))
            await asyncio.wait_for(service.tasks['claude'], 5)
            events = service.store.events('claude')
            assert events[-1]['status'] == 'ok', events[-1].get('error')
            assert len(requests) == 3
            assert 'private-thought' not in ''.join(e['delta'] for e in events if e['type'] == 'step.delta')
        finally:
            await service.close()


@pytest.mark.asyncio
async def test_real_bound_sdk_fallback_preserves_schema_and_counts_only_attempts(tmp_path):
    requests = []
    async def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        index = len(requests) - 1
        if index == 0:
            return httpx.Response(429, json={'error': {'message': 'rate limited', 'type': 'rate_limit_error'}})
        if index == 1:
            assert body['tool_choice']['function']['name'] == 'write_todos'
            return completion(body, index, 'write_todos', {'todos': [{'content': '检索', 'status': 'in_progress'}]})
        if index == 2:
            return completion(body, index, 'lookup')
        return completion(body, index, None)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        models = [with_transport(create_openai_compat(name, 'test-key'), client, False) for name in ('gpt-4o-mini', 'gpt-4o')]
        service = RuntimeService(tmp_path, model_factory=lambda _: FallbackChatModel(models),
            call_host=lambda op, *args, **kwargs: asyncio.sleep(0, result={'decision': 'allow', 'ticket': 't'} if op == 'authorize' else '材料'))
        await service.start()
        try:
            await service.submit(RunRequest(task_id='fallback', session_id='chat', text='检索', scope_ref='scope',
                workspace=str(tmp_path), mode='single-agent', models={'supervisor': {'model': 'test'}},
                tools=[ToolSpec(name='lookup', description='检索', input_schema={'type': 'object', 'properties': {}})]))
            await asyncio.wait_for(service.tasks['fallback'], 5)
            events = service.store.events('fallback')
            assert events[-1]['status'] == 'ok', events[-1].get('error')
            assert len(requests) == 4
            assert requests[1]['model'] == 'gpt-4o'
            budget = [event for event in events if event['type'] == 'budget.update'][-1]
            assert budget['steps'] == 4 and budget['tokens'] == 45
            first_usage = next(e for e in events if e['type'] == 'budget.update')
            assert first_usage['context_model'] == 'gpt-4o'
        finally:
            await service.close()


@pytest.mark.parametrize('first_response', ['prose', 'wrong_tool', 'never_plans'])
@pytest.mark.asyncio
async def test_auto_choice_cannot_execute_or_answer_before_real_plan(tmp_path, first_response):
    requests, executed = [], []
    async def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        index = len(requests) - 1
        if index == 0 or first_response == 'never_plans':
            reply = completion(body, index, 'lookup' if first_response == 'wrong_tool' else None)
            if not body.get('stream') and first_response != 'wrong_tool':
                wire = json.loads(reply.content)
                wire['choices'][0]['message']['content'] = 'PREPLAN正文不能显示'
                return httpx.Response(200, json=wire)
            return reply
        if index == 1:
            assert {t['function']['name'] for t in body['tools']} == {'write_todos', 'ask_human'}
            return completion(body, index, 'write_todos', {'todos': [{'content': '检索', 'status': 'in_progress'}]})
        if index == 2:
            return completion(body, index, 'lookup')
        return completion(body, index, None)
    async def host(op, *args, **kwargs):
        if op == 'execute':
            executed.append(args[1])
        return {'decision': 'allow', 'ticket': 't'} if op == 'authorize' else '材料'
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        original = create_openai_compat('local-tool-model', 'test-key', base_url='http://localhost:8000/v1')
        service = RuntimeService(tmp_path, model_factory=lambda _: with_transport(original, client, False), call_host=host)
        await service.start()
        try:
            await service.submit(RunRequest(task_id='plan', session_id='chat', text='检索', scope_ref='scope',
                workspace=str(tmp_path), mode='single-agent', models={'supervisor': {'model': 'local-tool-model'}},
                tools=[ToolSpec(name='lookup', description='检索', input_schema={'type': 'object', 'properties': {}})]))
            await asyncio.wait_for(service.tasks['plan'], 5)
            events = service.store.events('plan')
            assert 'PREPLAN' not in ''.join(e['delta'] for e in events if e['type'] == 'step.delta')
            if first_response == 'never_plans':
                assert events[-1]['status'] == 'error' and '未能发布步骤规划' in events[-1]['error']
                assert len(requests) == 3 and not executed
            else:
                assert events[-1]['status'] == 'ok', events[-1].get('error')
                assert executed == ['lookup'] and len(requests) == 4
        finally:
            await service.close()
