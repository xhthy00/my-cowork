"""Persist with the installed baseline, then resume with an upgraded shared backend.

Run prepare BEFORE changing uv.lock and verify AFTER uv sync. Only deterministic
models and local disposable side effects are used. Any checkpoint/API change
fails the candidate, leaving production on the previous complete release.
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from cowork_harness.service import RuntimeService
from runtime_contract import RunRequest, ToolSpec

class UpgradeModel(BaseChatModel):
    model_name: str = 'cowork:scripted'
    phase: str
    @property
    def _llm_type(self):
        return 'upgrade-contract'
    def bind_tools(self, tools, **kwargs):
        return self
    def _generate(self, messages, **kwargs):
        raise NotImplementedError
    async def _agenerate(self, messages, **kwargs):
        if self.phase == 'prepare':
            message = AIMessage(content='', tool_calls=[
                {'id': 'saved-effect', 'name': 'save_marker', 'args': {'content': 'once'}},
                {'id': 'pending-question', 'name': 'ask_human', 'args': {'question': '确认继续？'}}])
        else:
            assert any('once' in str(m.content) for m in messages), 'Lost completed tool result'
            assert any('继续' == m.content for m in messages), 'Lost resumed answer'
            message = AIMessage(content='upgrade-resumed')
        return ChatResult(generations=[ChatGeneration(message=message)])

async def run(phase, directory):
    directory.mkdir(parents=True, exist_ok=True)
    marker = directory / 'effects.json'
    async def call_host(op, cid, name, args, **kwargs):
        if op == 'authorize':
            return {'decision': 'allow', 'ticket': 'fixture'}
        ledger = json.loads(marker.read_text()) if marker.exists() else {}
        if cid not in ledger:
            ledger[cid] = args['content']
            marker.write_text(json.dumps(ledger))
        return ledger[cid]
    service = RuntimeService(directory / 'harness', model_factory=lambda _: UpgradeModel(phase=phase), call_host=call_host)
    await service.start()
    try:
        if phase == 'prepare':
            req = RunRequest(task_id='upgrade', session_id='upgrade', text='test', scope_ref='fixture',
                workspace=str(directory), mode='single-agent', models={'supervisor': {'model': 'fixture'}},
                tools=[ToolSpec(name='save_marker', description='Save a disposable marker.',
                    input_schema={'type': 'object', 'properties': {'content': {'type': 'string'}}, 'required': ['content']})])
            await service.submit(req)
        else:
            row = service.store.get('upgrade')
            assert row['status'] == 'waiting_user', row['status']
            await service.resume('upgrade', row['pending'][0]['interrupt_id'], {'answer': '继续'})
        await service.tasks['upgrade']
        row = service.store.get('upgrade')
        assert row['status'] == ('waiting_user' if phase == 'prepare' else 'succeeded'), service.store.events('upgrade')[-1]
        assert json.loads(marker.read_text()) == {'saved-effect': 'once'}
        if phase == 'verify':
            assert service.store.events('upgrade')[-1]['summary'] == 'upgrade-resumed'
        print(f'{phase}: checkpoint, pending input and completed tool result OK')
    finally:
        await service.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['prepare', 'verify'])
    parser.add_argument('--data-dir', type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.phase, args.data_dir))
