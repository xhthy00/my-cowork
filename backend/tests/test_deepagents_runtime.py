"""Upgrade contracts against real Deep Agents; models and external effects are deterministic."""
import asyncio
from pathlib import Path

import pytest
from langchain_core.tools import tool
from fastapi import HTTPException

from tests.conftest import FakeChatModel, make_ai
from runtime_contract import RunRequest, ToolSpec, ToolInvocation
from cowork_harness.service import RuntimeService
from cowork_harness.agent_factory import build_agent
from app.main import build_stack
from app.orchestrator.task_manager import TaskRequest
from app.host_capabilities.broker import CapabilityBroker
from app.observability.trace import TraceBus


def request(tmp_path, **kwargs):
    return RunRequest(task_id='run', session_id='chat', text='hello', scope_ref='scope',
        workspace=str(tmp_path), mode='single-agent', models={'supervisor': {'model': 'test'}}, **kwargs)


async def finish(service, req):
    await service.submit(req)
    await asyncio.wait_for(service.tasks[req.task_id], 5)
    return service.store.events(req.task_id)


@pytest.mark.asyncio
async def test_official_loop_and_session_continuity(tmp_path):
    class RecordingModel(FakeChatModel):
        seen: list = []
        async def _agenerate(self, messages, **kwargs):
            self.seen.append(messages)
            return await super()._agenerate(messages, **kwargs)
    model = RecordingModel(responses=[make_ai('first'), make_ai('second')])
    service = RuntimeService(tmp_path, model_factory=lambda _: model)
    await service.start()
    try:
        events = await finish(service, request(tmp_path))
        assert events[-1]['summary'] == 'first'
        req = request(tmp_path).model_copy(update={'task_id': 'run2', 'text': 'follow up'})
        assert (await finish(service, req))[-1]['summary'] == 'second'
        assert any(message.content == 'first' for message in model.seen[-1])
        assert [e['seq'] for e in events] == list(range(1, len(events) + 1))
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_single_agent_has_no_delegate_tool(tmp_path):
    model = FakeChatModel(responses=[make_ai('ok')])
    service = RuntimeService(tmp_path, model_factory=lambda _: model)
    await service.start()
    try:
        agent = build_agent(request(tmp_path), service.saver, lambda _: model, None, lambda _: None)
        # Public runnable graph node contains the tool node's public tool map.
        assert 'task' not in agent.get_graph().nodes['tools'].data.tools_by_name
        assert 'write_todos' in agent.get_graph().nodes['tools'].data.tools_by_name
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_scope_bound_approval_executes_once(tmp_path):
    target = tmp_path / 'hello.txt'
    model = FakeChatModel(responses=[
        make_ai(tool_calls=[{'id': 'write', 'name': 'fs_write', 'args': {'path': str(target), 'content': 'hi'}}]),
        make_ai('文件已保存'),
    ])
    manager = build_stack(supervisor_llm=model, whitelist=[str(tmp_path)])['task_manager']
    try:
        events = []
        async for event in manager.handle(TaskRequest(task_id='write1', session_id='chat', text='写文件',
                                                    session_mode='single-agent', enabled_skill_ids=[])):
            events.append(event)
            if event['type'] == 'tool.confirm_request':
                assert not target.exists()
                assert await manager.resolve('write1', event['call_id'], {'ok': True})
                assert not await manager.resolve('write1', event['call_id'], {'ok': True})
        assert events[-1]['status'] == 'ok', events[-1]
        assert target.read_text() == 'hi'
        assert [e['type'] for e in events].count('tool.result') == 1
        assert [e['type'] for e in events].count('graph.end') == 1
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_reject_never_executes(tmp_path):
    target = tmp_path / 'denied.txt'
    model = FakeChatModel(responses=[make_ai(tool_calls=[
        {'id': 'write', 'name': 'fs_write', 'args': {'path': str(target), 'content': 'hi'}}]), make_ai('已取消写入')])
    manager = build_stack(supervisor_llm=model, whitelist=[str(tmp_path)])['task_manager']
    try:
        async for event in manager.handle(TaskRequest(task_id='deny', text='写文件', session_mode='single-agent', enabled_skill_ids=[])):
            if event['type'] == 'tool.confirm_request':
                await manager.resolve('deny', event['call_id'], {'ok': False})
        assert not target.exists()
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_human_interrupt_survives_restart(tmp_path):
    model = FakeChatModel(responses=[make_ai(tool_calls=[
        {'id': 'question', 'name': 'ask_human', 'args': {'question': '选择格式', 'options': ['MD', 'PDF']}}]), make_ai('选择已收到')])
    service = RuntimeService(tmp_path, model_factory=lambda _: model)
    await service.start()
    await finish(service, request(tmp_path))
    pending = service.store.get('run')['pending'][0]
    assert service.store.get('run')['status'] == 'waiting_user'
    await service.close()
    service = RuntimeService(tmp_path, model_factory=lambda _: model)
    await service.start()
    try:
        assert service.store.get('run')['pending'][0]['interrupt_id'] == pending['interrupt_id']
        await service.resume('run', pending['interrupt_id'], {'answer': 'MD'})
        await service.tasks['run']
        assert service.store.get('run')['status'] == 'succeeded'
        assert service.store.events('run')[-1]['summary'] == '选择已收到'
        with pytest.raises(ValueError):
            await service.resume('run', pending['interrupt_id'], {'answer': 'PDF'})
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_workforce_uses_official_delegate(tmp_path):
    parent = FakeChatModel(responses=[make_ai(tool_calls=[{'id': 'delegate', 'name': 'task',
        'args': {'subagent_type': 'developer_agent', 'description': '检查项目'}}]), make_ai('项目检查完成')])
    child = FakeChatModel(responses=[make_ai('检查通过')])
    service = RuntimeService(tmp_path, model_factory=lambda spec: child if spec['model'] == 'child' else parent)
    await service.start()
    try:
        req = request(tmp_path).model_copy(update={'mode': 'workforce', 'models': {
            'supervisor': {'model': 'parent'}, 'developer_agent': {'model': 'child'}}})
        events = await finish(service, req)
        assert events[-1]['status'] == 'ok', events[-1]
        assert parent.idx == 2 and child.idx == 1
        assert any(e['type'] == 'agent.create' and e['agent_type'] == 'developer_agent' for e in events)
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_duplicate_submit_and_conflict(tmp_path):
    model = FakeChatModel(responses=[make_ai('ok')])
    service = RuntimeService(tmp_path, model_factory=lambda _: model)
    await service.start()
    try:
        req = request(tmp_path)
        await finish(service, req)
        assert (await service.submit(req))['created'] is False
        assert model.idx == 1
        with pytest.raises(ValueError):
            await service.submit(req.model_copy(update={'text': 'different'}))
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_cancel_waiting_interrupt_allows_next_turn(tmp_path):
    model = FakeChatModel(responses=[make_ai(tool_calls=[{'id': 'q', 'name': 'ask_human',
        'args': {'question': 'which?'}}]), make_ai('next')])
    service = RuntimeService(tmp_path, model_factory=lambda _: model)
    await service.start()
    try:
        req = request(tmp_path)
        await finish(service, req)
        assert await service.cancel('run')
        assert service.store.events('run')[-1]['status'] == 'cancelled'
        req = req.model_copy(update={'task_id': 'next'})
        assert (await finish(service, req))[-1]['summary'] == 'next'
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_internal_middleware_model_text_is_not_streamed_as_answer(tmp_path, monkeypatch):
    from langchain.agents.middleware import AgentMiddleware
    from langchain_core.messages import HumanMessage
    from cowork_harness import agent_factory

    internal = FakeChatModel(responses=[make_ai('INTERNAL SUMMARY'), make_ai('INTERNAL SUMMARY')])
    class SummarizeContext(AgentMiddleware):
        async def abefore_model(self, state, runtime):
            await internal.ainvoke([HumanMessage(content='Summarize context')])
    original = agent_factory.create_deep_agent
    def with_summary(**kwargs):
        kwargs['middleware'] = [*kwargs['middleware'], SummarizeContext()]
        return original(**kwargs)
    monkeypatch.setattr(agent_factory, 'create_deep_agent', with_summary)
    model = FakeChatModel(responses=[make_ai(tool_calls=[{'id': 'plan', 'name': 'write_todos',
        'args': {'todos': [{'content': '回答', 'status': 'in_progress'}]}}]), make_ai('正式回答')])
    service = RuntimeService(tmp_path, model_factory=lambda _: model)
    await service.start()
    try:
        events = await finish(service, request(tmp_path))
        assert events[-1]['status'] == 'ok', events[-1]
        visible = ''.join(event['delta'] for event in events if event['type'] == 'step.delta')
        assert visible == '正式回答'
        assert internal.idx == 2
    finally:
        await service.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['single-agent', 'workforce'])
async def test_initial_plan_is_bound_and_published_before_business_tools(tmp_path, mode):
    class RecordingModel(FakeChatModel):
        bindings: list = []
        def bind_tools(self, tools, **kwargs):
            self.bindings.append((kwargs.get('tool_choice'), [tool.name for tool in tools]))
            return self

    model = RecordingModel(responses=[
        make_ai(tool_calls=[{'id': 'plan', 'name': 'write_todos', 'args': {'todos': [
            {'content': '检索材料', 'status': 'in_progress'},
            {'content': '形成报告', 'status': 'pending'}]}}]),
        make_ai(tool_calls=[{'id': 'search', 'name': 'lookup', 'args': {}}]),
        make_ai('完成'),
    ])
    calls = []
    async def host(op, invocation_id, tool, args, **kwargs):
        calls.append(op)
        return {'decision': 'allow', 'ticket': 't'} if op == 'authorize' else '检索结果'
    service = RuntimeService(tmp_path, model_factory=lambda _: model, call_host=host)
    await service.start()
    try:
        req = request(tmp_path).model_copy(update={'mode': mode,
            'tools': [ToolSpec(name='lookup', description='检索材料', input_schema={'type': 'object', 'properties': {}})]})
        events = await finish(service, req)
        assert events[-1]['status'] == 'ok', events[-1]
        assert model.bindings[0] == ('write_todos', ['write_todos'])
        assert model.bindings[1][0] is None and 'lookup' in model.bindings[1][1]
        plan = next(event for event in events if event['type'] == 'todo_state' and event['todos'])
        action = next(event for event in events if event['type'] == 'tool.start' and event['tool'] == 'lookup')
        assert plan['seq'] < action['seq']
        assert [todo['content'] for todo in plan['todos']] == ['检索材料', '形成报告']
        assert calls == ['authorize', 'execute']
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_followup_gets_its_own_plan(tmp_path):
    class RecordingModel(FakeChatModel):
        choices: list = []
        def bind_tools(self, tools, **kwargs):
            self.choices.append(kwargs.get('tool_choice'))
            return self
    model = RecordingModel(responses=[
        make_ai(tool_calls=[{'id': 'plan1', 'name': 'write_todos', 'args': {'todos': [
            {'content': '首轮报告', 'status': 'completed'}]}}]), make_ai('首轮完成'),
        make_ai(tool_calls=[{'id': 'plan2', 'name': 'write_todos', 'args': {'todos': [
            {'content': '追问改稿', 'status': 'in_progress'}]}}]), make_ai('改稿完成'),
    ])
    service = RuntimeService(tmp_path, model_factory=lambda _: model)
    await service.start()
    try:
        await finish(service, request(tmp_path))
        events = await finish(service, request(tmp_path).model_copy(update={'task_id': 'followup', 'text': '改稿'}))
        assert events[-1]['status'] == 'ok'
        assert model.choices == ['write_todos', None, 'write_todos', None]
        assert next(e for e in events if e['type'] == 'todo_state' and e['todos'])['todos'][0]['content'] == '追问改稿'
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_interrupt_resume_keeps_published_plan(tmp_path):
    class RecordingModel(FakeChatModel):
        choices: list = []
        def bind_tools(self, tools, **kwargs):
            self.choices.append(kwargs.get('tool_choice'))
            return self
    model = RecordingModel(responses=[
        make_ai(tool_calls=[{'id': 'plan', 'name': 'write_todos', 'args': {'todos': [
            {'content': '确认格式并生成报告', 'status': 'in_progress'}]}}]),
        make_ai(tool_calls=[{'id': 'ask', 'name': 'ask_human', 'args': {'question': '格式？'}}]),
        make_ai('完成'),
    ])
    service = RuntimeService(tmp_path, model_factory=lambda _: model)
    await service.start()
    try:
        await finish(service, request(tmp_path))
        pending = service.store.get('run')['pending'][0]
        await service.resume('run', pending['interrupt_id'], {'answer': 'HTML'})
        await service.tasks['run']
        assert service.store.get('run')['status'] == 'succeeded'
        assert model.choices == ['write_todos', None, None]
        plans = [e['todos'] for e in service.store.events('run') if e['type'] == 'todo_state']
        assert len([plan for plan in plans if not plan]) == 1
        assert plans[-1][0]['content'] == '确认格式并生成报告'
    finally:
        await service.close()


def test_planning_call_disables_anthropic_thinking_without_mutating_normal_model():
    from cowork_harness.models import planning_model
    from model_integrations.anthropic import create_anthropic
    from model_integrations.fallback import FallbackChatModel
    model = create_anthropic('claude-sonnet-4-5', 'test-key')
    chain = FallbackChatModel([model])
    planner = planning_model(chain)
    assert planner.models[0].thinking is None
    assert model.thinking['type'] == 'enabled'
    bound = planner.bind_tools([{'name': 'write_todos', 'description': 'Plan',
        'parameters': {'type': 'object', 'properties': {}}}], tool_choice='write_todos')
    assert bound.models[0].kwargs['tool_choice'] == {'type': 'tool', 'name': 'write_todos'}


@pytest.mark.asyncio
async def test_parallel_sync_memory_tools_persist_events_without_failing_task(tmp_path):
    model = FakeChatModel(responses=[make_ai(tool_calls=[
        {'id': 'remember1', 'name': 'remember', 'args': {'content': '偏好一', 'scope': 'global'}},
        {'id': 'remember2', 'name': 'remember', 'args': {'content': '偏好二', 'scope': 'global'}},
    ]), make_ai('记忆已保存，报告已完成')])
    stack = build_stack(supervisor_llm=model, whitelist=[str(tmp_path)])
    manager = stack['task_manager']
    try:
        events = []
        async for event in manager.handle(TaskRequest(
                task_id='parallel-memory', session_id='chat', text='记住偏好',
                session_mode='single-agent', enabled_skill_ids=[])):
            events.append(event)
            if event['type'] == 'tool.confirm_request':
                assert await manager.resolve('parallel-memory', event['call_id'], {'ok': True})
        assert events[-1]['status'] == 'ok', events[-1]
        assert manager.status('parallel-memory') == 'DONE'
        assert 'storage_error' not in manager._tasks['parallel-memory']
        notices = [event for event in events if event['type'] == 'memory.saved']
        assert len(notices) == 2
        assert {event['payload']['content'] for event in notices} == {'偏好一', '偏好二'}
        durable = stack['task_store'].events('parallel-memory')
        assert len([row for row in durable if row['event']['type'] == 'memory.saved']) == 2
        trace = stack['trace_store'].list_for_task('parallel-memory')
        assert len([event for event in trace if event['type'] == 'memory.saved']) == 2
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_default_run_completes_above_200k_tokens(tmp_path, monkeypatch):
    monkeypatch.delenv('MY_COWORK_MAX_TOKENS', raising=False)
    first = make_ai(tool_calls=[{'id': 'todo', 'name': 'write_todos',
        'args': {'todos': [{'content': 'check', 'status': 'in_progress'}]}}])
    first.usage_metadata = {'input_tokens': 200000, 'output_tokens': 1000, 'total_tokens': 201000}
    second = make_ai('调研完成')
    second.usage_metadata = {'input_tokens': 10000, 'output_tokens': 1000, 'total_tokens': 11000}
    model = FakeChatModel(responses=[first, second])
    manager = build_stack(supervisor_llm=model, whitelist=[str(tmp_path)])['task_manager']
    try:
        assert manager.max_total_tokens is None
        events = [event async for event in manager.handle(TaskRequest(
            task_id='uncapped', text='调研', session_mode='single-agent', enabled_skill_ids=[]))]
        assert events[-1]['status'] == 'ok', events[-1]
        assert model.idx == 2
        usage = [event for event in events if event['type'] == 'budget.update'][-1]
        assert usage['tokens'] == 212000
        assert usage['max_tokens'] is None
        assert usage['input_tokens'] == 210000
        assert usage['output_tokens'] == 2000
    finally:
        await manager.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('limit, calls', [(1, 0), (200000, 1)])
async def test_explicit_token_cap_still_applies(tmp_path, limit, calls):
    response = make_ai('large response')
    response.usage_metadata = {'input_tokens': 200000, 'output_tokens': 1000, 'total_tokens': 201000}
    model = FakeChatModel(responses=[response])
    service = RuntimeService(tmp_path, model_factory=lambda _: model)
    await service.start()
    try:
        events = await finish(service, request(tmp_path, max_total_tokens=limit))
        assert events[-1]['status'] == 'error'
        assert 'Token budget exhausted' in events[-1]['error']
        assert model.idx == calls
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_budget_stops_model_before_next_request(tmp_path):
    model = FakeChatModel(responses=[make_ai(tool_calls=[{'id': 'todo', 'name': 'write_todos',
        'args': {'todos': [{'content': 'check', 'status': 'in_progress'}]}}]), make_ai('over budget')])
    service = RuntimeService(tmp_path, model_factory=lambda _: model)
    await service.start()
    try:
        events = await finish(service, request(tmp_path, max_steps=1))
        assert events[-1]['status'] == 'error'
        assert model.idx == 1
        assert '模型调用上限（1 次）' in events[-1]['error']
    finally:
        await service.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['single-agent', 'workforce'])
async def test_default_runtime_finishes_more_than_50_model_calls(tmp_path, mode):
    plan = make_ai(tool_calls=[{'id': 'plan', 'name': 'write_todos', 'args': {
        'todos': [{'content': '核验资料并交付报告', 'status': 'in_progress'}]}}])
    actions = [make_ai(tool_calls=[{'id': f'search-{i}', 'name': 'lookup', 'args': {}}]) for i in range(55)]
    if mode == 'workforce':
        parent = FakeChatModel(responses=[plan, make_ai(tool_calls=[{'id': 'delegate', 'name': 'task',
            'args': {'subagent_type': 'browser_agent', 'description': '核验资料'}}]), make_ai('调研报告已完成')])
        child = FakeChatModel(responses=[*actions, make_ai('核验完成')])
    else:
        parent = FakeChatModel(responses=[plan, *actions, make_ai('调研报告已完成')])
        child = parent
    calls = []
    async def host(op, *args, **kwargs):
        if op == 'execute': calls.append(args)
        return {'decision': 'allow', 'ticket': 't'} if op == 'authorize' else '核验材料'
    service = RuntimeService(tmp_path, model_factory=lambda spec: child if spec['model'] == 'child' else parent, call_host=host)
    await service.start()
    try:
        req = request(tmp_path).model_copy(update={'mode': mode, 'models': {
            'supervisor': {'model': 'parent'}, 'browser_agent': {'model': 'child'}},
            'tools': [ToolSpec(name='lookup', description='核验材料', input_schema={'type': 'object', 'properties': {}})]})
        assert req.max_steps is None
        events = await finish(service, req)
        assert events[-1]['status'] == 'ok', events[-1]
        assert events[-1]['summary'] == '调研报告已完成'
        usage = [event for event in events if event['type'] == 'budget.update'][-1]
        assert usage['steps'] == (59 if mode == 'workforce' else 57)
        assert usage['max_steps'] is None
        assert len(calls) == 55
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_default_host_passes_no_model_call_cap(tmp_path, monkeypatch):
    monkeypatch.delenv('MY_COWORK_MAX_STEPS', raising=False)
    tm = build_stack(supervisor_llm=FakeChatModel(responses=[make_ai('完成')]), whitelist=[str(tmp_path)])['task_manager']
    try:
        assert tm.max_steps is None
        events = [event async for event in tm.handle(TaskRequest(task_id='uncapped-steps', text='核验',
            session_mode='single-agent', enabled_skill_ids=[]))]
        assert events[-1]['status'] == 'ok'
        assert tm.runtime.embedded_service.store.get('uncapped-steps')['request']['max_steps'] is None
    finally:
        await tm.close()


@pytest.mark.asyncio
async def test_explicit_host_model_call_cap_is_forwarded_and_enforced(tmp_path, monkeypatch):
    monkeypatch.setenv('MY_COWORK_MAX_STEPS', '1')
    model = FakeChatModel(responses=[make_ai(tool_calls=[{'id': 'plan', 'name': 'write_todos',
        'args': {'todos': [{'content': '核验', 'status': 'in_progress'}]}}]), make_ai('不应请求')])
    tm = build_stack(supervisor_llm=model, whitelist=[str(tmp_path)])['task_manager']
    try:
        events = [event async for event in tm.handle(TaskRequest(task_id='explicit-steps', text='核验',
            session_mode='single-agent', enabled_skill_ids=[]))]
        assert events[-1]['status'] == 'error'
        assert '模型调用上限（1 次）' in events[-1]['error']
        assert model.idx == 1
    finally:
        await tm.close()


@pytest.mark.asyncio
async def test_broker_rejects_scope_and_ticket_tampering(tmp_path):
    @tool
    async def echo(text: str):
        """Echo text."""
        return text
    broker = CapabilityBroker(tmp_path, TraceBus())
    scope = broker.register([echo])
    body = ToolInvocation(scope_ref=scope, invocation_id='one', tool='echo', args={'text': 'hi'})
    try:
        authorization = await broker.authorize(body)
        assert authorization['decision'] == 'ask'
        with pytest.raises(HTTPException):
            await broker.execute(body.model_copy(update={'ticket': authorization['ticket']}))
        broker.approve(authorization['ticket'], True)
        with pytest.raises(HTTPException):
            await broker.execute(body.model_copy(update={'ticket': authorization['ticket'], 'args': {'text': 'changed'}}))
        body.ticket = authorization['ticket']
        assert await broker.execute(body) == 'hi'
        assert await broker.execute(body) == 'hi'
        with pytest.raises(HTTPException):
            await broker.authorize(body.model_copy(update={'scope_ref': 'foreign'}))
    finally:
        broker.close()


@pytest.mark.asyncio
async def test_filesystem_cannot_read_outside_workspace(tmp_path):
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    outside = tmp_path / 'secret.txt'
    outside.write_text('PRIVATE')
    model = FakeChatModel(responses=[make_ai(tool_calls=[{'id': 'escape', 'name': 'read_file',
        'args': {'file_path': '/../secret.txt'}}]), make_ai('done')])
    service = RuntimeService(tmp_path / 'state', model_factory=lambda _: model)
    await service.start()
    try:
        events = await finish(service, request(workspace))
        assert not any('PRIVATE' in str(e.get('result', '')) for e in events)
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_parent_child_share_model_budget(tmp_path):
    parent = FakeChatModel(responses=[make_ai(tool_calls=[{'id': 'delegate', 'name': 'task',
        'args': {'subagent_type': 'developer_agent', 'description': 'inspect'}}]), make_ai('blocked')])
    child = FakeChatModel(responses=[make_ai('child complete')])
    service = RuntimeService(tmp_path, model_factory=lambda spec: child if spec['model'] == 'child' else parent)
    await service.start()
    try:
        req = request(tmp_path, max_steps=2).model_copy(update={'mode': 'workforce', 'models': {
            'supervisor': {'model': 'parent'}, 'developer_agent': {'model': 'child'}}})
        events = await finish(service, req)
        assert events[-1]['status'] == 'error'
        assert parent.idx == child.idx == 1
        assert events[-1]['error'] == '已达到显式配置的模型调用上限（2 次），任务已停止'
    finally:
        await service.close()

@pytest.mark.asyncio
async def test_approval_scope_survives_host_restart(tmp_path):
    target = tmp_path / 'after-restart.txt'
    model = FakeChatModel(responses=[make_ai(tool_calls=[{'id': 'write', 'name': 'fs_write',
        'args': {'path': str(target), 'content': 'once'}}]), make_ai('saved')])
    first = build_stack(supervisor_llm=model, whitelist=[str(tmp_path)])['task_manager']
    stream = first.handle(TaskRequest(task_id='recover', session_id='recover', text='save',
        session_mode='single-agent', enabled_skill_ids=[]))
    async for event in stream:
        if event['type'] == 'tool.confirm_request':
            ticket = event['call_id']
            break
    await stream.aclose()
    await first.close()
    assert not target.exists()
    second = build_stack(supervisor_llm=model, whitelist=[str(tmp_path)])['task_manager']
    try:
        second.admission.pause()
        await second.recover()
        assert second.admission.status()['active'] == 1
        assert second.status('recover') == 'WAITING_USER'
        assert await second.resolve('recover', ticket, {'ok': True})
        await asyncio.wait_for(second._workers['recover'], 5)
        assert second.status('recover') == 'DONE'
        assert target.read_text() == 'once'
        ids = [r['event']['event_id'] for r in second.task_store.events('recover') if r['event'].get('event_id')]
        assert len(ids) == len(set(ids))
    finally:
        await second.close()

@pytest.mark.asyncio
async def test_builtin_workspace_denied_to_scoped_app(tmp_path):
    (tmp_path / 'private.txt').write_text('PRIVATE')
    model = FakeChatModel(responses=[make_ai(tool_calls=[{'id': 'read', 'name': 'read_file',
        'args': {'file_path': '/workspace/private.txt'}}]), make_ai('denied')])
    service = RuntimeService(tmp_path / 'state', model_factory=lambda _: model)
    await service.start()
    try:
        events = await finish(service, request(tmp_path).model_copy(update={'file_access': False}))
        assert not any('PRIVATE' in str(e.get('result')) for e in events)
        assert any('denied' in str(e.get('result', '')).lower() or 'permission' in str(e.get('result', '')).lower() for e in events)
    finally:
        await service.close()

@pytest.mark.asyncio
async def test_official_skills_use_scoped_resource_tree(tmp_path):
    from tests.test_bundled_skills import make_skills
    from app.runtime.app_context import AppTaskScope
    _, skills = make_skills(tmp_path)
    selected = 'app:cn.example.officecli:risk-analysis'
    model = FakeChatModel(responses=[make_ai('ready')])
    manager = build_stack(supervisor_llm=model, whitelist=[str(tmp_path)])['task_manager']
    try:
        req = await manager._prepare(TaskRequest(task_id='skills', text='分析风险', session_mode='single-agent',
            enabled_skill_ids=[selected], app_scope=AppTaskScope('cn.example.officecli', frozenset(), skills={selected: skills[selected]})))
        assert len(req.skills['supervisor']) == 1
        virtual = req.skills['supervisor'][0]
        entry = next(Path(req.skill_routes[virtual]).glob('*/SKILL.md'))
        assert 'RISK RULE' in entry.read_text() and 'REPORT RULE' not in entry.read_text()
        resource_path = virtual + entry.parent.name + '/references/rules.md'
        model.responses = [make_ai(tool_calls=[{'id': 'resource', 'name': 'read_file',
            'args': {'file_path': resource_path}}]), make_ai('ready')]
        await manager.runtime.start()
        events = await finish(manager.runtime.embedded_service, req)
        assert any('1.0.0: evidence required' in str(e.get('result')) for e in events)
    finally:
        await manager.close()

@pytest.mark.asyncio
async def test_interrupted_effect_is_never_replayed(tmp_path):
    entered = asyncio.Event()
    @tool
    async def delayed(text: str):
        """Disposable effect for cancellation contracts."""
        entered.set()
        await asyncio.Event().wait()
    broker = CapabilityBroker(tmp_path, TraceBus())
    scope = broker.register([delayed])
    body = ToolInvocation(scope_ref=scope, invocation_id='one', tool='delayed', args={'text': 'hi'})
    ticket = await broker.authorize(body)
    broker.approve(ticket['ticket'], True)
    body.ticket = ticket['ticket']
    operation = asyncio.create_task(broker.execute(body))
    await entered.wait()
    await broker.cancel_scope(scope)
    await asyncio.gather(operation, return_exceptions=True)
    assert (await broker.authorize(body))['decision'] == 'deny'
    broker.close()
    broker = CapabilityBroker(tmp_path, TraceBus())
    broker.register([delayed], ref=scope)
    try:
        assert (await broker.authorize(body))['decision'] == 'deny'
    finally:
        broker.close()

@pytest.mark.asyncio
async def test_child_tool_events_belong_to_delegate_instance(tmp_path):
    parent = FakeChatModel(responses=[make_ai(tool_calls=[{'id': 'worker-instance', 'name': 'task',
        'args': {'subagent_type': 'developer_agent', 'description': 'inspect'}}]), make_ai('done')])
    child = FakeChatModel(responses=[make_ai(tool_calls=[{'id': 'child-call', 'name': 'inspect', 'args': {}}]), make_ai('verified')])
    async def host(op, *args, **kwargs):
        return {'decision': 'allow', 'ticket': 'fixture'} if op == 'authorize' else 'inspected'
    service = RuntimeService(tmp_path, model_factory=lambda spec: child if spec['model'] == 'child' else parent, call_host=host)
    await service.start()
    try:
        req = request(tmp_path).model_copy(update={'mode': 'workforce', 'models': {
            'supervisor': {'model': 'parent'}, 'developer_agent': {'model': 'child'}},
            'tools': [ToolSpec(name='inspect', description='Inspect.', input_schema={'type': 'object', 'properties': {}},
                roles=['developer_agent'], metadata={'app_id': 'cn.test', 'type': 'malicious-override'})]})
        events = await finish(service, req)
        rows = [e for e in events if e.get('call_id') == 'child-call']
        assert [e['type'] for e in rows] == ['tool.start', 'tool.result']
        assert all(e['agent_id'] == 'worker-instance' and e['app_id'] == 'cn.test' for e in rows)
    finally:
        await service.close()

@pytest.mark.asyncio
async def test_same_task_replay_after_restart_does_not_call_model(tmp_path):
    model = FakeChatModel(responses=[make_ai('once')])
    req = TaskRequest(task_id='replay', text='hello', session_mode='single-agent', enabled_skill_ids=[])
    first = build_stack(supervisor_llm=model, whitelist=[str(tmp_path)])['task_manager']
    assert [e async for e in first.handle(req)][-1]['summary'] == 'once'
    await first.close()
    second = build_stack(supervisor_llm=model, whitelist=[str(tmp_path)])['task_manager']
    try:
        await second.recover()
        assert [e async for e in second.handle(req)][-1]['summary'] == 'once'
        assert model.idx == 1
        with pytest.raises(ValueError):
            await second.submit(TaskRequest(task_id='replay', text='changed'))
    finally:
        await second.close()

@pytest.mark.asyncio
async def test_edited_plan_resumes_without_reasking(tmp_path):
    class Observe(FakeChatModel):
        seen: list = []
        async def _agenerate(self, messages, **kwargs):
            self.seen = messages
            return await super()._agenerate(messages, **kwargs)
    model = Observe(responses=[make_ai(tool_calls=[{'id': 'plan', 'name': 'propose_plan',
        'args': {'subtasks': [{'content': 'original'}]}}]), make_ai('edited plan received')])
    service = RuntimeService(tmp_path, model_factory=lambda _: model)
    await service.start()
    try:
        await finish(service, request(tmp_path))
        pending = service.store.get('run')['pending'][0]
        assert pending['kind'] == 'plan'
        await service.resume('run', pending['interrupt_id'], {'subtasks': [{'content': 'edited'}]})
        await service.tasks['run']
        assert service.store.get('run')['status'] == 'succeeded'
        assert any('edited' in str(m.content) for m in model.seen)
        assert len([e for e in service.store.events('run') if e['type'] == 'to_sub_tasks']) == 1
    finally:
        await service.close()

@pytest.mark.asyncio
async def test_remote_numeric_reply_resumes_official_question(tmp_path):
    from app.server.channels.manager import ChannelManager
    from app.server.channels.store import ChannelStore
    from unittest.mock import AsyncMock
    model = FakeChatModel(responses=[make_ai(tool_calls=[{'id': 'q', 'name': 'ask_human',
        'args': {'question': '格式？', 'options': ['Markdown', 'PDF']}}]), make_ai('received')])
    manager = build_stack(supervisor_llm=model, whitelist=[str(tmp_path)])['task_manager']
    stream = manager.handle(TaskRequest(task_id='remote', text='write', source='lark',
        session_mode='single-agent', enabled_skill_ids=[]))
    async for event in stream:
        if event['type'] == 'human.ask':
            question_id = event['question_id']
            break
    channel = ChannelManager(ChannelStore(tmp_path / 'channels.db'), manager, send=AsyncMock())
    key = ('lark', 'sender', 'chat')
    channel._human_questions[key] = [('remote', question_id)]
    try:
        await channel._reply_to_human_question(key, 'remote', question_id, '2')
        await asyncio.wait_for(manager._workers['remote'], 5)
        answers = [e['answer'] for e in manager._tasks['remote']['events'] if e['type'] == 'human.answered']
        assert answers == ['PDF'] and key not in channel._human_questions
    finally:
        await stream.aclose()
        await manager.close()

@pytest.mark.asyncio
async def test_upgrade_snapshot_keeps_pending_checkpoint(tmp_path):
    import json, sqlite3
    model = FakeChatModel(responses=[make_ai(tool_calls=[{'id': 'question', 'name': 'ask_human',
        'args': {'question': 'continue?'}}]), make_ai('resumed')])
    service = RuntimeService(tmp_path, model_factory=lambda _: model)
    await service.start()
    await finish(service, request(tmp_path))
    pending = service.store.get('run')['pending'][0]
    await service.close()
    manifest = tmp_path / 'build-identity.json'
    old = json.loads(manifest.read_text())
    old['deepagents_version'] = '0.0.0'
    manifest.write_text(json.dumps(old))
    service = RuntimeService(tmp_path, model_factory=lambda _: model)
    await service.start()
    try:
        backup = next((tmp_path / 'upgrade-backups').glob('*'))
        with sqlite3.connect(backup / 'runs.db') as db:
            assert db.execute('SELECT status FROM runs WHERE id="run"').fetchone()[0] == 'waiting_user'
        assert (backup / 'checkpoints.db').is_file()
        await service.resume('run', pending['interrupt_id'], {'answer': 'yes'})
        await service.tasks['run']
        assert service.store.get('run')['status'] == 'succeeded'
    finally:
        await service.close()

@pytest.mark.asyncio
async def test_remote_plan_does_not_wait_for_desktop_confirmation(tmp_path):
    model = FakeChatModel(responses=[make_ai(tool_calls=[{'id': 'plan', 'name': 'propose_plan',
        'args': {'subtasks': [{'content': '检索'}]}}]), make_ai('远程任务完成')])
    manager = build_stack(supervisor_llm=model, whitelist=[str(tmp_path)])['task_manager']
    try:
        events = [e async for e in manager.handle(TaskRequest(task_id='remote-plan', source='lark',
            text='检索', session_mode='workforce', enabled_skill_ids=[]))]
        assert events[-1]['status'] == 'ok'
        assert not any(e['type'] == 'to_sub_tasks' for e in events)
    finally:
        await manager.close()

@pytest.mark.asyncio
async def test_fallback_model_keeps_single_agent_tool_scope(tmp_path):
    from model_integrations.fallback import FallbackChatModel
    class RecordingModel(FakeChatModel):
        bound_names: list[str] = []
        def bind_tools(self, tools, **kwargs):
            self.bound_names = [getattr(tool, 'name', '') for tool in tools]
            return self
    inner = RecordingModel(responses=[make_ai(tool_calls=[{'id': 'plan', 'name': 'write_todos',
        'args': {'todos': [{'content': '答复', 'status': 'in_progress'}]}}]), make_ai('ok')])
    model = FallbackChatModel([inner])
    service = RuntimeService(tmp_path, model_factory=lambda _: model)
    await service.start()
    try:
        events = await finish(service, request(tmp_path))
        assert events[-1]['status'] == 'ok'
        assert {'read_file', 'write_todos'} <= set(inner.bound_names)
        assert 'task' not in inner.bound_names
        assert not {'write_file', 'edit_file', 'delete', 'execute'} & set(inner.bound_names)
    finally:
        await service.close()

@pytest.mark.asyncio
async def test_stale_confirmation_skips_not_yet_submitted_tasks(tmp_path):
    manager = build_stack(supervisor_llm=FakeChatModel(responses=[make_ai('unused')]), whitelist=[str(tmp_path)])['task_manager']
    try:
        assert not await manager.resolve('not-yet-created', 'stale-ticket', {'ok': True})
    finally:
        await manager.close()

@pytest.mark.parametrize('task_id', ['../drain', 'a/b', '..'])
def test_run_id_cannot_change_rpc_route(tmp_path, task_id):
    from pydantic import ValidationError
    payload = request(tmp_path).model_dump()
    payload['task_id'] = task_id
    with pytest.raises(ValidationError):
        RunRequest.model_validate(payload)

@pytest.mark.asyncio
async def test_runtime_failure_stops_outstanding_host_effect(tmp_path):
    entered = asyncio.Event()
    @tool
    async def delayed():
        """Disposable effect for terminal failure contracts."""
        entered.set()
        await asyncio.Event().wait()
    delayed.metadata = {'tool_access': 'read'}
    manager = build_stack(supervisor_llm=FakeChatModel(responses=[make_ai('unused')]), whitelist=[str(tmp_path)])['task_manager']
    manager.tools.append(delayed)
    req = TaskRequest(task_id='terminal-error', text='test', session_mode='single-agent', enabled_skill_ids=[])
    prepared = await manager._prepare(req)
    manager._requests[req.task_id] = req
    manager._set_status(req.task_id, 'RUNNING')
    body = ToolInvocation(scope_ref=prepared.scope_ref, invocation_id='effect', tool='delayed')
    grant = await manager.broker.authorize(body)
    body.ticket = grant['ticket']
    effect = asyncio.create_task(manager.broker.execute(body))
    async def failed_events(*args, **kwargs):
        yield {'type': 'graph.end', 'task_id': req.task_id, 'status': 'error', 'error': 'model failed'}
    manager.runtime.events = failed_events
    try:
        await entered.wait()
        await manager._consume(req, prepared.model_dump(), 0)
        await asyncio.gather(effect, return_exceptions=True)
        assert effect.cancelled()
        assert manager.status(req.task_id) == 'FAILED'
        assert (await manager.broker.authorize(body))['decision'] == 'deny'
    finally:
        await manager.close()

@pytest.mark.asyncio
async def test_failed_run_does_not_poison_next_conversation_turn(tmp_path):
    model = FakeChatModel(responses=[])
    service = RuntimeService(tmp_path, model_factory=lambda _: model)
    await service.start()
    try:
        req = request(tmp_path)
        assert (await finish(service, req))[-1]['status'] == 'error'
        original = service.store.get('run')['thread_id']
        model.responses = [make_ai('next turn succeeds')]
        next_req = req.model_copy(update={'task_id': 'next', 'text': 'try again'})
        assert (await finish(service, next_req))[-1]['summary'] == 'next turn succeeds'
        assert service.store.get('next')['thread_id'] != original
    finally:
        await service.close()

@pytest.mark.asyncio
async def test_busy_turn_keeps_original_pending_session_epoch(tmp_path):
    model = FakeChatModel(responses=[make_ai(tool_calls=[{'id': 'q', 'name': 'ask_human',
        'args': {'question': 'continue?'}}]), make_ai('original completed'), make_ai('next completed')])
    service = RuntimeService(tmp_path, model_factory=lambda _: model)
    await service.start()
    try:
        req = request(tmp_path)
        await finish(service, req)
        original = service.store.get('run')
        busy = req.model_copy(update={'task_id': 'busy'})
        assert (await finish(service, busy))[-1]['status'] == 'error'
        pending = original['pending'][0]
        await service.resume('run', pending['interrupt_id'], {'answer': 'yes'})
        await service.tasks['run']
        assert service.store.get('run')['status'] == 'succeeded'
        next_req = req.model_copy(update={'task_id': 'next'})
        assert (await finish(service, next_req))[-1]['summary'] == 'next completed'
        assert service.store.get('next')['thread_id'] == original['thread_id']
    finally:
        await service.close()
