"""Clarifications use the existing form contract and resume the same graph."""
import asyncio
import json

import httpx
import pytest

from app.main import build_stack, create_app
from app.orchestrator.task_manager import TaskRequest
from cowork_harness.agent_factory import CLARIFICATION_INSTRUCTIONS, interaction_tools
from cowork_harness.service import RuntimeService
from runtime_contract import RunRequest
from tests.conftest import FakeChatModel, make_ai
from model_integrations.openai_compat import create_openai_compat
from tests.test_model_compatibility_matrix import completion, with_transport


FIELDS = [
    {'label': 'FED 所指行业', 'kind': 'single', 'options': ['场发射显示', '前端开发', '联邦快递', '美联储'], 'required': True, 'placeholder': ''},
    {'label': '报告用途', 'kind': 'single', 'options': ['行业研究', '入行参考'], 'required': False, 'placeholder': ''},
    {'label': '其他范围', 'kind': 'text', 'options': [], 'required': False, 'placeholder': '可补充地区、时间范围'},
]
ANSWER = '1. FED 所指行业：前端开发\n2. 报告用途：入行参考'

# Shape captured from the failed MiniMax-M3 run: singleton XML array wrappers,
# question instead of label, option objects and a string boolean.
MINIMAX_QUESTION = {
    'question': '您想调研的FED具体指哪个领域？',
    'fields': {'item': {'kind': 'single', 'options': {'item': [
        {'label': '美联储（Federal Reserve）', 'description': '美国中央银行的政策走向、利率决议、宏观经济影响等'},
        {'label': '场发射显示（Field Emission Display）', 'description': '新一代显示技术，包括原理、市场前景、竞争格局等'},
        {'label': '前端开发（Front-End Development）', 'description': 'Web/移动端前端工程师职业前景、技术栈趋势等'},
        {'label': '柔性电子设备（Flexible Electronics）', 'description': '柔性显示、柔性传感器等可穿戴设备相关行业'},
    ]}, 'question': '您想调研的FED具体指哪个领域？', 'required': 'true'}},
}


def plan(status='in_progress'):
    return make_ai(tool_calls=[{'id': 'plan-' + status, 'name': 'write_todos',
        'args': {'todos': [{'content': '确认行业后调研', 'status': status}]}}])


def question():
    return make_ai(tool_calls=[{'id': 'clarify', 'name': 'ask_human',
        'args': {'question': '请确认 FED 所指行业', 'fields': FIELDS}}])


def test_model_can_see_the_form_field_schema():
    schema = interaction_tools()[0].args_schema.model_json_schema()
    field = schema['$defs']['HumanQuestionField']
    assert field['properties']['kind']['enum'] == ['single', 'multiple', 'text']
    assert {'label', 'kind'} <= set(field['required'])
    assert {'options', 'required', 'placeholder'} <= set(field['properties'])


@pytest.mark.parametrize('streaming', [False, True])
@pytest.mark.asyncio
async def test_minimax_captured_question_before_plan_displays_form_and_resumes(tmp_path, streaming):
    requests = []
    async def handler(request):
        body = json.loads(request.content)
        index = len(requests)
        requests.append(body)
        if index < 2:
            assert body.get('tool_choice') == 'auto'
            assert {t['function']['name'] for t in body['tools']} == {'write_todos', 'ask_human'}
        if index == 0:
            return completion(body, index, 'ask_human', MINIMAX_QUESTION, reasoning='reasoning')
        if index == 1:
            assert next(m for m in body['messages'] if m['role'] == 'tool')['content'] == ANSWER
            return completion(body, index, 'write_todos', {'todos': [{'content': '调研前端开发行业', 'status': 'in_progress'}]}, reasoning='reasoning')
        return completion(body, index, None, reasoning='reasoning')

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        original = create_openai_compat('MiniMax-M3', 'test-key', base_url='https://api.minimaxi.com/v1')
        model = with_transport(original, client, streaming)
        service = RuntimeService(tmp_path, model_factory=lambda _: model)
        await service.start()
        try:
            await service.submit(RunRequest(task_id='minimax-form', session_id='s', text='帮我调研FED行业前景',
                mode='workforce', scope_ref='t', workspace=str(tmp_path), models={'supervisor': {'model': 'MiniMax-M3'}}))
            await asyncio.wait_for(service.tasks['minimax-form'], 5)
            assert len(requests) == 1  # The first ask must execute instead of being rejected as premature.
            row = service.store.get('minimax-form')
            assert row['status'] == 'waiting_user', service.store.events('minimax-form')[-1]
            event = next(e for e in service.store.events('minimax-form') if e['type'] == 'human.ask')
            assert event['fields'] == [{
                'label': MINIMAX_QUESTION['question'], 'kind': 'single', 'required': True, 'placeholder': '',
                'options': [o['label'] for o in MINIMAX_QUESTION['fields']['item']['options']['item']],
            }]
            assert not any(e['type'] == 'graph.end' for e in service.store.events('minimax-form'))
            await service.resume('minimax-form', row['pending'][0]['interrupt_id'], {'answer': ANSWER})
            await asyncio.wait_for(service.tasks['minimax-form'], 5)
            assert service.store.events('minimax-form')[-1]['summary'] == '回答完成'
            assert len(requests) == 3
        finally:
            await service.close()


@pytest.mark.parametrize('mode', ['single-agent', 'workforce'])
@pytest.mark.asyncio
async def test_form_is_pending_until_reply_and_survives_restart(tmp_path, mode):
    class RecordingModel(FakeChatModel):
        seen: list = []
        async def _agenerate(self, messages, **kwargs):
            self.seen.append(messages)
            return await super()._agenerate(messages, **kwargs)
    model = RecordingModel(responses=[plan(), question(), plan('completed'), make_ai('按前端开发方向继续调研')])
    service = RuntimeService(tmp_path, model_factory=lambda _: model)
    await service.start()
    try:
        await service.submit(RunRequest(task_id='form', session_id='s', text='帮我调研 FED 行业前景', mode=mode,
            workspace=str(tmp_path), scope_ref='t', models={'supervisor': {'model': 'test'}}))
        await asyncio.wait_for(service.tasks['form'], 5)
        row = service.store.get('form')
        pending = row['pending'][0]
        assert row['status'] == 'waiting_user'
        assert model.idx == 2
        events = service.store.events('form')
        assert not any(e['type'] == 'graph.end' for e in events)
        event = next(e for e in events if e['type'] == 'human.ask')
        assert event['fields'] == FIELDS
        assert event['question_id'] == pending['interrupt_id']
        assert CLARIFICATION_INSTRUCTIONS in model.seen[-1][0].text
        await service.close()
        service = RuntimeService(tmp_path, model_factory=lambda _: model)
        await service.start()
        assert service.store.get('form')['pending'][0]['fields'] == FIELDS
        await service.resume('form', pending['interrupt_id'], {'answer': ANSWER})
        await asyncio.wait_for(service.tasks['form'], 5)
        assert service.store.get('form')['thread_id'] == row['thread_id']
        assert service.store.events('form')[-1]['summary'] == '按前端开发方向继续调研'
        assert any(m.type == 'tool' and m.content == ANSWER for m in model.seen[-1])
        assert sum(e['type'] == 'human.ask' for e in service.store.events('form')) == 1
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_existing_form_reply_route_continues_the_original_task(tmp_path):
    model = FakeChatModel(responses=[plan(), question(), plan('completed'), make_ai('调研完成')])
    manager = build_stack(supervisor_llm=model, whitelist=[str(tmp_path)])['task_manager']
    app = create_app(task_manager=manager)
    events = []
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            async for event in manager.handle(TaskRequest(task_id='form-http', session_id='s', text='帮我调研 FED 行业前景',
                                                        session_mode='single-agent', enabled_skill_ids=[])):
                events.append(event)
                if event['type'] == 'human.ask':
                    assert manager.status('form-http') == 'WAITING_USER'
                    pending = await client.get('/api/chat/form-http/pending-questions')
                    assert pending.json()['questions'][0]['fields'] == FIELDS
                    response = await client.post('/api/chat/form-http/human-reply', json={
                        'question_id': event['question_id'], 'answer': ANSWER})
                    assert response.status_code == 200
            assert events[-1]['summary'] == '调研完成'
            assert manager.status('form-http') == 'DONE'
            assert any(e['type'] == 'human.answered' and e['answer'] == ANSWER for e in events)
            assert sum(e['type'] == 'graph.start' for e in events) == 1
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_delegated_agent_can_ask_the_same_form(tmp_path):
    class RecordingModel(FakeChatModel):
        seen: list = []
        async def _agenerate(self, messages, **kwargs):
            self.seen.append(messages)
            return await super()._agenerate(messages, **kwargs)
    parent = FakeChatModel(responses=[plan(), make_ai(tool_calls=[{'id': 'delegate', 'name': 'task',
        'args': {'subagent_type': 'browser_agent', 'description': '核实 FED 所指方向并调研'}}]), make_ai('调研完成')])
    child = RecordingModel(responses=[question(), make_ai('前端开发方向')])
    service = RuntimeService(tmp_path, model_factory=lambda spec: child if spec['model'] == 'child' else parent)
    await service.start()
    try:
        await service.submit(RunRequest(task_id='delegated', session_id='s', text='调研 FED',
            workspace=str(tmp_path), scope_ref='t', mode='workforce',
            models={'supervisor': {'model': 'parent'}, 'browser_agent': {'model': 'child'}}))
        await asyncio.wait_for(service.tasks['delegated'], 5)
        row = service.store.get('delegated')
        assert row['status'] == 'waiting_user'
        assert row['pending'][0]['fields'] == FIELDS
        assert CLARIFICATION_INSTRUCTIONS in child.seen[0][0].text
        await service.resume('delegated', row['pending'][0]['interrupt_id'], {'answer': ANSWER})
        await asyncio.wait_for(service.tasks['delegated'], 5)
        assert service.store.events('delegated')[-1]['summary'] == '调研完成'
        assert any(m.type == 'tool' and m.content == ANSWER for m in child.seen[-1])
    finally:
        await service.close()
