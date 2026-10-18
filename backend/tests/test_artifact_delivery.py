"""Deliverables survive the host/runtime boundary, including unchanged reports."""
import asyncio
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.main import build_stack
from app.orchestrator.task_manager import TaskRequest
from app.sandbox.path_guard import PathGuard
from app.workspace.artifacts import paths_in_answer, paths_in_write_result, verified_artifact
from tests.conftest import FakeChatModel, make_ai
from langchain_core.messages import AIMessage, HumanMessage
from cowork_harness.deliverables import preserve_html


def test_answer_paths_with_chinese_spaces_parentheses_and_file_urls(tmp_path):
    report = tmp_path / '各地人工智能产业赋能中心 报告（2026年10月14日合并版）.html'
    report.write_text('<h1>报告</h1>')
    guard = PathGuard([str(tmp_path)])
    for text in [f'交付文件：`{report}`', f'交付文件：{report}\n已核验', f'[报告](<{report}>)', f'[报告]({report.as_uri()})']:
        found = {verified_artifact(raw, str(tmp_path), guard) for raw in paths_in_answer(text)}
        assert str(report) in found
    assert verified_artifact('/workspace/' + report.name, str(tmp_path), guard) == str(report)
    assert verified_artifact(report.name, str(tmp_path), guard) == str(report)
    assert paths_in_write_result(f'Wrote 100 characters to {report}') == [str(report)]
    assert paths_in_write_result('{"path": "report.html"}') == ['report.html']


def test_rejects_nonexistent_unapproved_process_files_and_symlink_escape(tmp_path):
    root = tmp_path / 'workspace'; root.mkdir()
    other = tmp_path / 'outside.html'; other.write_text('outside')
    helper = root / '_build_report.py'; helper.write_text('pass')
    link = root / 'link.html'; link.symlink_to(other)
    guard = PathGuard([str(root)])
    for path in [root / 'missing.html', other, helper, link, root]:
        assert verified_artifact(str(path), str(root), guard) is None
    scope = SimpleNamespace(artifacts=[], files={}, output_dir=str(root / 'output'))
    source = root / 'source.html'; source.write_text('input')
    assert verified_artifact(str(source), str(root), PathGuard([str(tmp_path)]), scope) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['write_text_result', 'command_scan', 'existing_report', 'missing_report'])
async def test_task_emits_verified_html_artifact_before_end(tmp_path, monkeypatch, kind):
    root = tmp_path / 'work'; root.mkdir()
    report = root / '调研报告（合并版）.html'
    old = root / '未交付的旧稿.html'; old.write_text('old')
    past = time.time() - 300
    os.utime(old, (past, past))
    if kind == 'existing_report':
        report.write_text('<h1>合并版</h1>')
        os.utime(report, (past, past))
    tm = build_stack(supervisor_llm=FakeChatModel(responses=[make_ai('unused')]), whitelist=[str(root)])['task_manager']
    async def submit(request): return None
    async def events(task_id):
        if kind in {'write_text_result', 'command_scan'}:
            report.write_text('<h1>合并版</h1>')
            yield {'type': 'tool.result', 'task_id': task_id, 'tool': 'fs_write' if kind == 'write_text_result' else 'bash',
                   'result': f'Wrote 15 characters to {report}' if kind == 'write_text_result' else '{"stdout":"ok","returncode":0}'}
        summary = '合并报告已就绪。' if kind in {'write_text_result', 'command_scan'} else f'交付文件：`{report}`'
        yield {'type': 'graph.end', 'task_id': task_id, 'status': 'ok', 'summary': summary}
    monkeypatch.setattr(tm.runtime, 'submit', submit)
    monkeypatch.setattr(tm.runtime, 'events', events)
    try:
        rows = [row async for row in tm.handle(TaskRequest(task_id='deliver', text='交付报告', session_mode='single-agent',
            enabled_skill_ids=[], space_root_path=str(root), workdir_mode='direct-write'))]
        assert rows[-1]['status'] == 'ok', rows[-1]
        artifacts = [row['path'] for row in rows if row['type'] == 'artifact.file']
        assert artifacts == ([] if kind == 'missing_report' else [str(report)])
        if kind == 'existing_report':
            assert report.stat().st_mtime == past
    finally:
        await tm.close()


def test_final_acknowledgement_cannot_erase_html_from_a_tool_call_message():
    source = '<!doctype html><html><body><h1>行业报告</h1></body></html>'
    draft = make_ai('<think>internal</think>\n```html\n' + source + '\n```', tool_calls=[{
        'id': 'todos', 'name': 'write_todos', 'args': {'todos': []}}])
    messages = [HumanMessage('HTML报告'), draft, AIMessage('请自行保存')]
    result = preserve_html(messages, '请自行保存')
    assert source in result and '尚未确认保存' in result and 'internal' not in result
    # An earlier turn's report must never be revived for a new unrelated task.
    assert preserve_html([*messages, HumanMessage('你好'), AIMessage('你好')], '你好') == '你好'
    incomplete = make_ai('```html\n<html><body>not complete\n```')
    assert preserve_html([HumanMessage('报告'), incomplete], '结束') == '结束'


@pytest.mark.asyncio
@pytest.mark.parametrize('allow', [True, False])
async def test_inline_html_is_saved_via_host_approval_before_file_delivery(tmp_path, allow):
    root = tmp_path / 'work'; root.mkdir()
    report = root / 'FED_行业前景.html'
    source = '<!doctype html><html lang="zh-CN"><head><title>FED 行业前景</title></head><body><h1>报告内容</h1></body></html>'
    plan = lambda status: [{'content': '撰写 HTML 报告并交付', 'status': status}]
    model = FakeChatModel(responses=[
        make_ai(tool_calls=[{'id': 'ask', 'name': 'ask_human', 'args': {'question': '调研结果形式？', 'options': ['HTML报告', '文字']}}]),
        make_ai(tool_calls=[{'id': 'plan', 'name': 'write_todos', 'args': {'todos': plan('in_progress')}}]),
        make_ai('```html\n' + source + '\n```', tool_calls=[{'id': 'complete', 'name': 'write_todos', 'args': {'todos': plan('completed')}}]),
        make_ai('完整 HTML 代码已交付，可自行保存为 FED_行业前景.html。'),
        make_ai(tool_calls=[{'id': 'save', 'name': 'fs_write', 'args': {'path': str(report), 'content': source}}]),
        make_ai('报告已保存：`' + str(report) + '`' if allow else '未获准保存'),
    ])
    manager = build_stack(supervisor_llm=model, whitelist=[str(root)])['task_manager']
    rows = []
    try:
        async for event in manager.handle(TaskRequest(task_id='inline-html', text='调研FED行业前景', session_id='s',
            session_mode='single-agent', enabled_skill_ids=[], space_root_path=str(root), workdir_mode='direct-write')):
            rows.append(event)
            if event['type'] == 'human.ask':
                await manager.resolve('inline-html', event['question_id'], {'answer': 'HTML报告'})
            if event['type'] == 'tool.confirm_request':
                assert not report.exists()
                await manager.resolve('inline-html', event['call_id'], {'ok': allow})
        assert rows[-1]['status'] == 'ok', rows[-1]
        assert model.idx == 6  # Recovery runs through the official model/tool graph.
        artifacts = [e for e in rows if e['type'] == 'artifact.file']
        if allow:
            assert report.read_text() == source
            assert [e['path'] for e in artifacts] == [str(report)]
            assert source not in rows[-1]['summary']
        else:
            assert not report.exists() and not artifacts
            assert source in rows[-1]['summary'] and '尚未确认保存' in rows[-1]['summary']
        assert sum(e['type'] == 'tool.confirm_request' for e in rows) == 1
    finally:
        await manager.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('query,expected_calls', [('生成HTML报告', 5), ('解释这个HTML示例', 3)])
async def test_html_save_repair_is_bounded_and_does_not_force_examples_to_disk(tmp_path, query, expected_calls):
    from cowork_harness.service import RuntimeService
    from runtime_contract import RunRequest, ToolSpec
    source = '<html><body>complete document</body></html>'
    model = FakeChatModel(responses=[
        make_ai(tool_calls=[{'id': 'plan', 'name': 'write_todos', 'args': {'todos': [{'content': '回答', 'status': 'in_progress'}]}}]),
        make_ai('```html\n' + source + '\n```', tool_calls=[{'id': 'complete', 'name': 'write_todos', 'args': {'todos': [{'content': '回答', 'status': 'completed'}]}}]),
        make_ai('请自行保存'), make_ai('请自行保存'), make_ai('请自行保存'),
    ])
    service = RuntimeService(tmp_path, model_factory=lambda _: model)
    await service.start()
    try:
        await service.submit(RunRequest(task_id='bounded', session_id='s', text=query, workspace=str(tmp_path),
            scope_ref='t', mode='single-agent', models={'supervisor': {'model': 'test'}},
            tools=[ToolSpec(name='fs_write', description='Write a file', input_schema={'type': 'object', 'properties': {}})]))
        await asyncio.wait_for(service.tasks['bounded'], 5)
        end = service.store.events('bounded')[-1]
        assert end['status'] == 'ok'
        assert source in end['summary'] and '尚未确认保存' in end['summary']
        assert model.idx == expected_calls
        assert not list(tmp_path.glob('*.html'))
    finally:
        await service.close()
