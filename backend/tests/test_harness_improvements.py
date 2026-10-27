"""Regression replays through real Deep Agents and host capability boundaries."""
import asyncio
import contextvars
import json
from pathlib import Path

import httpx
import pytest
from jsonschema import ValidationError
from langchain_core.messages import HumanMessage, ToolMessage

from app.host_capabilities.broker import CapabilityBroker
from app.observability.trace import TraceBus
from app.runtime_client.client import RuntimeClient
from app.sandbox.path_guard import PathGuard, PathGuardError, task_path_guard
from app.skills import SkillMeta
from app.skills.snapshots import SkillSnapshots
from app.tools.mcp.manager import McpManager
from cowork_harness.events import DeltaBuffer
from cowork_harness.service import RuntimeService
from deepagents.middleware.summarization import compute_summarization_defaults
from model_integrations.fallback import FallbackChatModel
from runtime_contract import RunRequest, ToolInvocation, ToolSpec
from runtime_contract.tool_results import RESULT_TAG
from tests.conftest import FakeChatModel, make_ai


def req(root, **kwargs):
    return RunRequest(task_id='run', session_id='session', text='核验', workspace=str(root),
        scope_ref='fixture', mode='single-agent', models={'supervisor': {'model': 'parent'}}, **kwargs)


class RecordingModel(FakeChatModel):
    seen: list = []
    bindings: list = []

    def bind_tools(self, tools, **kwargs):
        self.bindings.append([tool.get('name') if isinstance(tool, dict) else tool.name for tool in tools])
        return self

    async def _agenerate(self, messages, **kwargs):
        self.seen.append(messages)
        return await super()._agenerate(messages, **kwargs)


def test_task_guard_does_not_accumulate_other_tasks_grants(tmp_path):
    durable = PathGuard([str(tmp_path / 'shared')])
    first, second = durable.for_task(), durable.for_task()
    first.add_whitelist(str(tmp_path / 'a'))
    second.add_whitelist(str(tmp_path / 'b'))
    context_a, context_b = contextvars.copy_context(), contextvars.copy_context()
    context_a.run(task_path_guard.set, first)
    context_b.run(task_path_guard.set, second)
    context_a.run(durable.check_path, str(tmp_path / 'a' / 'report.txt'))
    context_b.run(durable.check_path, str(tmp_path / 'b' / 'report.txt'))
    with pytest.raises(PathGuardError):
        context_a.run(durable.check_path, str(tmp_path / 'b' / 'report.txt'))
    with pytest.raises(PathGuardError):
        durable.check_path(str(tmp_path / 'a' / 'report.txt'))


class McpSession:
    name = 'fixture'

    def __init__(self):
        self.calls = []

    def rpc(self, method, args):
        self.calls.append(args)
        return {'content': [{'type': 'text', 'text': 'caption'},
            {'type': 'image', 'data': 'AAAA', 'mimeType': 'image/png'}],
            'structuredContent': {'count': 1}}


def mcp_tool(session):
    return McpManager()._make_wrapper(session, 'fixture', {'name': 'inspect', 'inputSchema': {
        'type': 'object', 'properties': {'count': {'type': 'integer', 'minimum': 1},
        'mode': {'type': 'string', 'enum': ['safe']}, 'nullable': {'type': ['string', 'null']}},
        'required': ['count', 'mode'], 'additionalProperties': False}})


def test_mcp_preserves_schema_and_rejects_invalid_arguments_before_rpc():
    session = McpSession()
    tool = mcp_tool(session)
    assert tool.args_schema['required'] == ['count', 'mode']
    for args in ({'count': '1', 'mode': 'safe'}, {'count': 0, 'mode': 'safe'},
                 {'count': 1}, {'count': 1, 'mode': 'other'}, {'count': 1, 'mode': 'safe', 'extra': 1}):
        with pytest.raises(ValidationError):
            tool.invoke(args)
    assert not session.calls
    result = tool.invoke({'count': 1, 'mode': 'safe', 'nullable': None})
    assert result[RESULT_TAG] == 1
    assert result['content'][1] == {'type': 'image', 'base64': 'AAAA', 'mime_type': 'image/png'}
    assert json.loads(result['content'][2]['text']) == {'count': 1}
    assert session.calls[0]['arguments']['nullable'] is None


@pytest.mark.asyncio
async def test_mcp_invalid_parameters_do_not_receive_an_execution_ticket(tmp_path):
    broker = CapabilityBroker(tmp_path, TraceBus())
    tool = mcp_tool(McpSession())
    scope = broker.register([tool])
    try:
        result = await broker.authorize(ToolInvocation(scope_ref=scope, invocation_id='bad',
            tool=tool.name, args={'count': 'bad', 'mode': 'safe'}))
        assert result['decision'] == 'deny'
        assert broker.db.execute('SELECT COUNT(*) FROM invocations').fetchone()[0] == 0
    finally:
        broker.close()


@pytest.mark.asyncio
async def test_image_blocks_reach_model_after_host_rpc_and_checkpoint(tmp_path):
    model = RecordingModel(responses=[make_ai(tool_calls=[{'id': 'image', 'name': 'inspect', 'args': {}}]), make_ai('图片已核验')])
    async def host(op, *args, **kwargs):
        return {'decision': 'allow', 'ticket': 'ok'} if op == 'authorize' else {
            RESULT_TAG: 1, 'content': [{'type': 'text', 'text': 'caption'},
            {'type': 'image', 'base64': 'AAAA', 'mime_type': 'image/png'}], 'is_error': False}
    service = RuntimeService(tmp_path, model_factory=lambda _: model, call_host=host)
    await service.start()
    try:
        await service.submit(req(tmp_path, tools=[ToolSpec(name='inspect', description='Inspect image', input_schema={'type': 'object'})]))
        await service.tasks['run']
        assert service.store.get('run')['status'] == 'succeeded'
        tool_message = next(m for m in model.seen[-1] if isinstance(m, ToolMessage) and m.tool_call_id == 'image')
        assert tool_message.content[1]['type'] == 'image'
        assert tool_message.content[1]['base64'] == 'AAAA'
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_delegates_receive_scoped_memory(tmp_path):
    memory = tmp_path / 'memory'; memory.mkdir()
    (memory / 'AGENTS.md').write_text('PROJECT_MEMORY_SENTINEL: use the approved report template.')
    parent = RecordingModel(responses=[make_ai(tool_calls=[{'id': 'delegate', 'name': 'task',
        'args': {'subagent_type': 'document_agent', 'description': '核验报告'}}]), make_ai('已核验')])
    child = RecordingModel(responses=[make_ai('已遵循项目模板')])
    service = RuntimeService(tmp_path / 'state', model_factory=lambda spec: child if spec['model'] == 'child' else parent)
    await service.start()
    try:
        request = req(tmp_path, confirm_plan=False, memory_paths=['/memories/AGENTS.md'], skill_routes={'/memories/': str(memory)}).model_copy(update={
            'mode': 'workforce', 'models': {'supervisor': {'model': 'parent'}, 'document_agent': {'model': 'child'}}})
        await service.submit(request); await service.tasks['run']
        assert service.store.get('run')['status'] == 'succeeded'
        assert any('PROJECT_MEMORY_SENTINEL' in str(m.content) for m in child.seen[0])
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_plan_confirmation_blocks_direct_delegation_and_resumes_with_edits(tmp_path):
    task = lambda cid, description: make_ai(tool_calls=[{'id': cid, 'name': 'task',
        'args': {'subagent_type': 'developer_agent', 'description': description}}])
    parent = RecordingModel(responses=[task('premature', 'original'),
        make_ai(tool_calls=[{'id': 'approval', 'name': 'propose_plan', 'args': {'subtasks': [{'content': 'original'}]}}]),
        task('approved', 'edited'), make_ai('已完成')])
    child = RecordingModel(responses=[make_ai('edited complete')])
    factory = lambda spec: child if spec['model'] == 'child' else parent
    directory = tmp_path / 'state'
    service = RuntimeService(directory, model_factory=factory)
    await service.start()
    request = req(tmp_path).model_copy(update={'mode': 'workforce',
        'models': {'supervisor': {'model': 'parent'}, 'developer_agent': {'model': 'child'}}})
    await service.submit(request); await service.tasks['run']
    assert child.idx == 0
    assert 'task' not in parent.bindings[0]
    row = service.store.get('run')
    assert row['status'] == 'waiting_user'
    await service.close()
    service = RuntimeService(directory, model_factory=factory)
    await service.start()
    try:
        await service.resume('run', row['pending'][0]['interrupt_id'], {'subtasks': [{'content': 'edited'}]})
        await service.tasks['run']
        assert service.store.get('run')['status'] == 'succeeded'
        assert child.idx == 1
        assert any('edited' in str(m.content) for m in child.seen[0])
        assert len([e for e in service.store.events('run') if e['type'] == 'to_sub_tasks']) == 1
    finally:
        await service.close()


def test_fallback_compaction_respects_the_smallest_known_model_window():
    models = [FakeChatModel(profile={'max_input_tokens': 1_000_000, 'tool_calling': True}),
              FakeChatModel(profile={'max_input_tokens': 32_000})]
    model = FallbackChatModel(models).bind_tools([])
    assert model.profile['max_input_tokens'] == 32_000
    assert model.profile['tool_calling'] is True
    assert compute_summarization_defaults(model)['trigger'] == ('fraction', 0.85)


@pytest.mark.asyncio
async def test_answer_fragments_are_batched_and_flushed_before_interrupts_and_completion():
    events = []
    writer = DeltaBuffer(events.append, interval=0.001)
    for char in '完整答复':
        writer.emit({'type': 'step.delta', 'delta': char})
    await asyncio.sleep(0.01)
    writer.emit({'type': 'step.delta', 'delta': '后续'})
    writer.emit({'type': 'human.ask', 'question': '确认？'})
    writer.emit({'type': 'step.delta', 'delta': '结束'})
    writer.emit({'type': 'graph.end'})
    writer.close()
    assert [event['type'] for event in events] == ['step.delta', 'step.delta', 'human.ask', 'step.delta', 'graph.end']
    assert ''.join(e['delta'] for e in events if e['type'] == 'step.delta') == '完整答复后续结束'


def test_skill_snapshots_reuse_content_and_detect_resource_changes(tmp_path, monkeypatch):
    source = tmp_path / 'source'; source.mkdir()
    resource = source / 'reference.txt'; resource.write_text('version one')
    skill = SkillMeta(id='fixture', prompt='Use reference.txt', base_dir=source)
    snapshots = SkillSnapshots(tmp_path / 'snapshots')
    first = snapshots.prepare(skill)
    original_open = Path.open
    reads = []
    def track(path, *args, **kwargs):
        if path == resource: reads.append(path)
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', track)
    assert snapshots.prepare(skill) == first
    assert not reads
    resource.write_text('version two')
    second = snapshots.prepare(skill)
    assert first[0] != second[0]
    assert (first[1] / first[2] / 'reference.txt').read_text() == 'version one'
    assert (second[1] / second[2] / 'reference.txt').read_text() == 'version two'
    (source / 'link').symlink_to(resource)
    with pytest.raises(ValueError, match='links'):
        snapshots.prepare(skill)


@pytest.mark.asyncio
async def test_sse_reconnect_uses_cursor_without_replaying_received_events(tmp_path):
    after = []
    def response(request):
        after.append(request.url.params['after'])
        events = ([{'seq': 1, 'type': 'graph.start'}] if len(after) == 1 else
            [{'seq': 1, 'type': 'graph.start'}, {'seq': 2, 'type': 'graph.end', 'status': 'ok'}])
        return httpx.Response(200, text=''.join('data: ' + json.dumps(event) + '\n\n' for event in events))
    client = RuntimeClient(tmp_path, None)
    client.http = httpx.AsyncClient(base_url='http://fixture', transport=httpx.MockTransport(response))
    try:
        events = [event async for event in client.events('run')]
        assert [e['seq'] for e in events] == [1, 2]
        assert after == ['0', '1']
    finally:
        await client.close()


@pytest.mark.parametrize('text,expected', [('你好', False), ('解释 list 和 tuple 的区别', False),
    ('你好，请删除文件', True), ('解释之后生成报告文件', True), ('搜索最新价格', True)])
def test_simple_question_fast_path_preserves_action_planning(text, expected):
    from app.runtime.task_policy import planning_required
    assert planning_required(text) is expected


@pytest.mark.asyncio
async def test_simple_answers_do_not_force_planning_or_lose_conversation_history(tmp_path):
    model = RecordingModel(responses=[make_ai('你好'), make_ai('继续回答')])
    service = RuntimeService(tmp_path, model_factory=lambda _: model)
    await service.start()
    try:
        request = req(tmp_path, planning_required=False)
        await service.submit(request); await service.tasks['run']
        await service.submit(request.model_copy(update={'task_id': 'followup', 'planning_required': True}))
        await service.tasks['followup']
        assert any(message.content == '你好' for message in model.seen[-1])
        assert service.store.get('run')['thread_id'] == service.store.get('followup')['thread_id']
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_small_fallback_is_not_called_with_an_oversized_prompt():
    class Unavailable(FakeChatModel):
        async def _agenerate(self, messages, **kwargs):
            raise RuntimeError('503 unavailable')
    primary = Unavailable(profile={'max_input_tokens': 1_000_000})
    fallback = FakeChatModel(responses=[make_ai('should not run')], profile={'max_input_tokens': 32})
    with pytest.raises(ValueError, match='上下文'):
        await FallbackChatModel([primary, fallback]).ainvoke([HumanMessage('context ' * 300)])
    assert fallback.idx == 0


@pytest.mark.parametrize('extension', ['docx', 'pptx', 'xlsx', 'pdf', 'json'])
def test_deliverable_validator_rejects_empty_and_corrupt_files(tmp_path, extension):
    from app.workspace.validation import validate_deliverable
    path = tmp_path / ('report.' + extension)
    path.write_bytes(b'')
    assert validate_deliverable(path) == '交付文件为空'
    path.write_text('not a valid document')
    assert validate_deliverable(path)


@pytest.mark.asyncio
async def test_missing_deliverable_cannot_be_reported_as_success(tmp_path, monkeypatch):
    from app.main import build_stack
    from app.orchestrator.task_manager import TaskRequest
    manager = build_stack(supervisor_llm=FakeChatModel(responses=[make_ai('unused')]), whitelist=[str(tmp_path)])['task_manager']
    async def submit(request):
        return None
    async def events(task_id):
        yield {'type': 'graph.end', 'status': 'ok', 'summary': '文件已生成', 'payload': {'status': 'ok'}}
    monkeypatch.setattr(manager.runtime, 'submit', submit)
    monkeypatch.setattr(manager.runtime, 'events', events)
    try:
        rows = [event async for event in manager.handle(TaskRequest(task_id='missing-file', text='生成 Word 文档',
            session_mode='single-agent', enabled_skill_ids=[]))]
        assert rows[-1]['status'] == rows[-1]['payload']['status'] == 'error'
        assert rows[-1]['delivery_validation'] == 'failed'
        assert manager.status('missing-file') == 'FAILED'
        assert not [event for event in rows if event['type'] == 'artifact.file']
    finally:
        await manager.close()


def test_role_tool_sets_are_specific_and_unassigned_tools_stay_with_supervisor(tmp_path):
    from app.main import build_stack
    manager = build_stack(supervisor_llm=FakeChatModel(responses=[]), whitelist=[str(tmp_path)])['task_manager']
    try:
        assert 'pptx_gen' in manager.role_tools['document_agent']
        assert 'pptx_gen' not in manager.role_tools['developer_agent']
        assert 'bash' not in manager.role_tools['browser_agent']
        assert 'lark_send_message' not in set.union(*manager.role_tools.values())
    finally:
        asyncio.run(manager.close())


@pytest.mark.asyncio
async def test_scheduled_workforce_adopts_existing_plan_without_waiting_for_desktop(tmp_path):
    from app.main import build_stack
    from app.orchestrator.task_manager import TaskRequest
    manager = build_stack(supervisor_llm=FakeChatModel(responses=[]), whitelist=[str(tmp_path)])['task_manager']
    try:
        request = await manager._prepare(TaskRequest(task_id='scheduled', text='执行已创建的定时任务',
            source='schedule', session_mode='workforce', enabled_skill_ids=[]))
        assert request.confirm_plan is False
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_delivery_failure_survives_host_restart_without_replaying_model(tmp_path):
    from app.main import build_stack
    from app.orchestrator.task_manager import TaskRequest
    request = TaskRequest(task_id='delivery-replay', text='生成 Word 文档', session_mode='single-agent', enabled_skill_ids=[])
    first = build_stack(supervisor_llm=FakeChatModel(responses=[make_ai('文件已生成')]), whitelist=[str(tmp_path)])['task_manager']
    rows = [event async for event in first.handle(request)]
    assert rows[-1]['delivery_validation'] == 'failed'
    await first.close()
    unused = FakeChatModel(responses=[])
    second = build_stack(supervisor_llm=unused, whitelist=[str(tmp_path)])['task_manager']
    try:
        replay = [event async for event in second.handle(request)]
        assert replay[-1]['delivery_validation'] == 'failed'
        assert replay[-1]['payload']['status'] == 'error'
        assert second.status(request.task_id) == 'FAILED'
        assert unused.idx == 0
    finally:
        await second.close()


@pytest.mark.asyncio
async def test_buffer_write_failure_still_emits_terminal_error(tmp_path, monkeypatch):
    model = FakeChatModel(responses=[make_ai('streamed answer')])
    service = RuntimeService(tmp_path, model_factory=lambda _: model)
    await service.start()
    original = service.store.event
    def fail_delta(run_id, event):
        if event['type'] == 'step.delta':
            raise OSError('temporary event write failure')
        return original(run_id, event)
    monkeypatch.setattr(service.store, 'event', fail_delta)
    try:
        await service.submit(req(tmp_path, planning_required=False))
        await asyncio.wait_for(service.tasks['run'], 5)
        assert service.store.get('run')['status'] == 'failed'
        assert service.store.events('run')[-1]['status'] == 'error'
        assert 'temporary event write failure' in service.store.events('run')[-1]['error']
    finally:
        await service.close()


def test_requested_output_format_does_not_confuse_conversion_input_with_output():
    from app.workspace.validation import requested_formats
    assert requested_formats('把 PDF 转成 Word 文档') == {'.docx', '.doc'}
    assert requested_formats('生成 PPT《2026Q1》2 页') == {'.pptx', '.ppt'}
    assert requested_formats('解释 PDF 格式') == set()
