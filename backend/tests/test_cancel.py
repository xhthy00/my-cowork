"""Cancel a real Deep Agents model call through the product API."""
import asyncio
import pytest
from app.main import build_stack
from app.orchestrator.task_manager import TaskRequest
from tests.conftest import FakeChatModel, make_ai

@pytest.mark.asyncio
async def test_task_manager_cancel(tmp_path):
    started, cancelled = asyncio.Event(), asyncio.Event()
    class SlowModel(FakeChatModel):
        async def _agenerate(self, messages, **kwargs):
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
    manager = build_stack(supervisor_llm=SlowModel(responses=[make_ai('unused')]),
                          whitelist=[str(tmp_path)])['task_manager']
    try:
        await manager.submit(TaskRequest(task_id='slow', text='wait', session_mode='single-agent', enabled_skill_ids=[]))
        await asyncio.wait_for(started.wait(), 5)
        assert manager.cancel('slow')
        await asyncio.wait_for(cancelled.wait(), 5)
        await asyncio.wait_for(manager._workers['slow'], 5)
        assert manager.status('slow') == 'CANCELLED'
        assert manager.admission.status()['active'] == 0
        assert len([e for e in manager._tasks['slow']['events'] if e['type'] == 'graph.end']) == 1
    finally:
        await manager.close()
