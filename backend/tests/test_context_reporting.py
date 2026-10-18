"""The displayed window belongs to the root model, not accumulated task usage."""
import asyncio
import pytest
from cowork_harness.service import RuntimeService
from runtime_contract import RunRequest
from tests.conftest import FakeChatModel, make_ai
from model_integrations.context import selection_key


@pytest.mark.asyncio
async def test_subagent_context_does_not_replace_root_context(tmp_path):
    delegate = make_ai(tool_calls=[{'id': 'delegate', 'name': 'task', 'args': {
        'subagent_type': 'browser_agent', 'description': '核验'}}])
    final = make_ai('完成')
    child_result = make_ai('核验完成')
    for message, tokens in [(delegate, 100), (final, 200), (child_result, 9000)]:
        message.usage_metadata = {'input_tokens': tokens, 'output_tokens': 10, 'total_tokens': tokens + 10}
    parent = FakeChatModel(responses=[delegate, final], metadata={'cowork_context_limit': 1_000_000, 'cowork_context_key': 'root'})
    child = FakeChatModel(responses=[child_result], metadata={'cowork_context_limit': 32_000, 'cowork_context_key': 'child'})
    service = RuntimeService(tmp_path, model_factory=lambda spec: child if spec['model'] == 'child' else parent)
    await service.start()
    try:
        await service.submit(RunRequest(task_id='context',session_id='s',text='核验',scope_ref='t',workspace=str(tmp_path),
            models={'supervisor': {'model': 'parent'}, 'browser_agent': {'model': 'child'}}))
        await asyncio.wait_for(service.tasks['context'], 5)
        events = service.store.events('context')
        assert events[-1]['status'] == 'ok', events[-1]
        usage = [event for event in events if event['type'] == 'budget.update']
        assert [event['context_tokens'] for event in usage if 'context_tokens' in event] == [100, 200]
        assert usage[-1]['input_tokens'] == 9300
        assert usage[-1]['context_limit'] == 1_000_000
        assert usage[-1]['context_key'] == selection_key({'model': 'parent'})
    finally:
        await service.close()
