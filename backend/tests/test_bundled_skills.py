import shutil
import json
from types import SimpleNamespace

import pytest

from app.skills import find_skill, bundled_skill_scope
from app.skills.bundled import load_package_skills
from app.skills.config import delete_skill, patch_skill_config, list_skills_api
from app.runtime.app_context import AppTaskScope, app_task_scope
from app.runtime.v2.assemble import assemble_system_messages
from app.tools.builtin.skills import make_skill_tools
from app.industry_apps.package import inspect_zip, AppPackageError
from test_industry_apps import EXAMPLE, PACK_SCRIPT
from test_industry_ai import setup, body


def make_skills(tmp_path, app_id='cn.example.officecli', version='1.0.0'):
    package = tmp_path / app_id / version
    for local, text in [('risk-analysis', 'RISK RULE: cite task evidence'), ('weekly-report', 'REPORT RULE: progress and next steps')]:
        directory = package / 'skills' / local
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'SKILL.md').write_text(f'---\nname: Same title\ndescription: Test method\n---\n{text}\n', encoding='utf-8')
        (directory / 'references').mkdir(exist_ok=True)
        (directory / 'references' / 'rules.md').write_text(f'{version}: evidence required', encoding='utf-8')
    manifest = {'id': app_id, 'name': 'Example', 'version': version, 'skills': ['skills/risk-analysis', 'skills/weekly-report']}
    return manifest, load_package_skills(manifest, package)


def test_collision_and_readonly_management(tmp_path):
    _, skills = make_skills(tmp_path)
    _, other = make_skills(tmp_path, 'cn.other.app')
    user = tmp_path / 'user' / 'risk-analysis'
    user.mkdir(parents=True)
    (user / 'SKILL.md').write_text('---\nname: Same title\n---\nUSER RULE', encoding='utf-8')
    with bundled_skill_scope({**skills, **other}):
        assert find_skill('Same title', root=user.parent).prompt == 'USER RULE'
        assert 'RISK RULE' in find_skill('app:cn.example.officecli:risk-analysis').prompt
        rows = list_skills_api(root=user.parent, config_path=tmp_path/'cfg.json')
        assert len(rows) == 5
        with pytest.raises(ValueError, match='插件'):
            delete_skill('app:cn.example.officecli:risk-analysis', root=user.parent)
        with pytest.raises(ValueError, match='插件'):
            patch_skill_config('app:cn.example.officecli:risk-analysis', {'enabled': False}, tmp_path/'cfg.json')
        assert (user/'SKILL.md').exists()


def test_ordinary_chat_preloads_exact_plugin_identity(tmp_path):
    _, skills = make_skills(tmp_path)
    key = 'app:cn.example.officecli:risk-analysis'
    with bundled_skill_scope(skills):
        text = '\n'.join(str(m.content) for m in assemble_system_messages(enabled_skill_ids=[key], user_text='分析风险', long_term=SimpleNamespace()))
        assert key in text and 'RISK RULE' in text and 'REPORT RULE' not in text


def test_plugin_display_name_cannot_authorize_disabled_user_skill(tmp_path):
    _, skills = make_skills(tmp_path)
    user = tmp_path/'user'/'disabled'
    user.mkdir(parents=True)
    (user/'SKILL.md').write_text('---\nname: Same title\n---\nDISABLED USER RULE', encoding='utf-8')
    cfg = tmp_path/'config.json'
    cfg.write_text(json.dumps({'skills': {'Same title': {'enabled': False}}}), encoding='utf-8')
    with bundled_skill_scope(skills):
        tools = {tool.name: tool for tool in make_skill_tools('single_agent', root=user.parent, config_path=cfg)}
        result = tools['load_skill'].invoke({'name': 'Same title'})
        assert result.startswith('[ERROR]') and 'DISABLED USER RULE' not in result
        assert 'RISK RULE' in tools['load_skill'].invoke({'name': 'app:cn.example.officecli:risk-analysis'})


@pytest.mark.parametrize('prompt', ['分析风险', '只写 Markdown，说明 Word 交付情况'])
def test_exact_app_selection_bypasses_office_inference(tmp_path, prompt):
    _, skills = make_skills(tmp_path)
    selected = {'app:cn.example.officecli:risk-analysis': skills['app:cn.example.officecli:risk-analysis']}
    token = app_task_scope.set(AppTaskScope('cn.example.officecli', frozenset(), skills=selected))
    try:
        with bundled_skill_scope(skills):
            messages = assemble_system_messages(enabled_skill_ids=list(selected), user_text=prompt, long_term=SimpleNamespace())
        text = '\n'.join(str(m.content) for m in messages)
        assert 'RISK RULE' in text
        assert 'REPORT RULE' not in text
        assert '<preloaded_skill name="officecli' not in text
        assert 'read_skill_resource' in text
    finally:
        app_task_scope.reset(token)


def test_resources_are_scoped_and_versions_stay_together(tmp_path):
    _, skills = make_skills(tmp_path)
    key = 'app:cn.example.officecli:risk-analysis'
    token = app_task_scope.set(AppTaskScope('cn.example.officecli', frozenset({'read_skill_resource'}), skills={key: skills[key]}))
    try:
        with bundled_skill_scope(skills, selected={key: skills[key]}):
            tools = {t.name: t for t in make_skill_tools('single_agent', root=tmp_path/'user', config_path=tmp_path/'cfg.json')}
            read = tools['read_skill_resource']
            assert '1.0.0: evidence' in read.invoke({'name': key, 'path': 'references/rules.md'})
            assert '[ERROR]' in read.invoke({'name': key, 'path': '../../weekly-report/SKILL.md'})
            assert '[ERROR]' in read.invoke({'name': 'app:cn.example.officecli:weekly-report', 'path': 'SKILL.md'})
    finally:
        app_task_scope.reset(token)


def test_zip_validates_skill_contents_before_install(tmp_path):
    import importlib.util
    import yaml
    source = tmp_path/'source'
    shutil.copytree(EXAMPLE, source)
    manifest_file = source/'mycowork-app.yaml'
    manifest = yaml.safe_load(manifest_file.read_text(encoding='utf-8'))
    manifest['skills'] = ['skills/risk-analysis']
    manifest_file.write_text(yaml.safe_dump(manifest), encoding='utf-8')
    directory = source/'skills/risk-analysis'
    directory.mkdir(parents=True, exist_ok=True)
    entry = directory/'SKILL.md'
    entry.write_text('---\nname: Risk\n---\nRISK RULE', encoding='utf-8')
    spec = importlib.util.spec_from_file_location('pack_a3', PACK_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    archive = tmp_path/'app.zip'
    module.pack(source, archive)
    assert inspect_zip(archive.read_bytes()).manifest.skills == ['skills/risk-analysis']
    for content in ['---\nname: Risk\nschedule: daily\n---\nRULE', '---\nname: [bad]\n---\nRULE', '---\nname: Risk\n---\n']:
        entry.write_text(content, encoding='utf-8')
        with pytest.raises(AppPackageError, match='skill'):
            module.pack(source, tmp_path / 'invalid.zip')
        assert not (tmp_path / 'invalid.zip').exists()


@pytest.mark.asyncio
async def test_request_and_followup_bind_selected_skills(setup, tmp_path):
    client, store, submitted, app = setup
    manifest, skills = make_skills(tmp_path, 'cn.test.one')
    app.state.app_skills = skills
    app.state.app_manifests['cn.test.one']['skills'] = manifest['skills']
    response = await client.post('/api/industry-ai/cn.test.one/tasks', json=body(skills=['risk-analysis', 'risk-analysis']))
    assert response.status_code == 200, response.text
    task = response.json()
    assert submitted[0].enabled_skill_ids == ['app:cn.test.one:risk-analysis']
    assert len(submitted[0].app_scope.skills) == 1
    store.upsert(task['task_id'], 'DONE')
    next_run = await client.post('/api/industry-ai/cn.test.one/tasks', json=body(request_id='next', parent_task_id=task['task_id'], skills=['weekly-report']))
    assert next_run.status_code == 200, next_run.text
    assert submitted[-1].enabled_skill_ids == submitted[0].enabled_skill_ids
    store.upsert(next_run.json()['task_id'], 'DONE')
    invalid = await client.post('/api/industry-ai/cn.test.one/tasks', json=body(request_id='invalid', skills=['unlisted']))
    assert invalid.status_code == 403
    assert len(submitted) == 2


@pytest.mark.asyncio
async def test_loaded_record_is_actual_preload_and_survives_cursor(setup, tmp_path):
    client, store, submitted, app = setup
    manifest, skills = make_skills(tmp_path, 'cn.test.one')
    app.state.app_skills = skills
    app.state.app_manifests['cn.test.one']['skills'] = manifest['skills']
    started = (await client.post('/api/industry-ai/cn.test.one/tasks', json=body(skills=['risk-analysis']))).json()
    url = f'/api/industry-ai/cn.test.one/tasks/{started["task_id"]}'
    assert (await client.get(url)).json()['loaded_skills'] == []
    token = app_task_scope.set(submitted[0].app_scope)
    try:
        assemble_system_messages(user_text='分析', long_term=SimpleNamespace())
    finally:
        app_task_scope.reset(token)
    assert (await client.get(url+'?after=1000')).json()['loaded_skills'] == [
        {'id': 'app:cn.test.one:risk-analysis', 'name': 'Same title', 'version': '1.0.0'}]


@pytest.mark.asyncio
async def test_empty_and_unavailable_selection(setup, tmp_path):
    client, store, submitted, app = setup
    manifest, skills = make_skills(tmp_path, 'cn.test.one')
    app.state.app_skills = skills
    app.state.app_manifests['cn.test.one']['skills'] = manifest['skills']
    response = await client.post('/api/industry-ai/cn.test.one/tasks', json=body(prompt='说明 Word 交付'))
    assert response.status_code == 200
    assert submitted[0].enabled_skill_ids == []
    token = app_task_scope.set(submitted[0].app_scope)
    try:
        text = '\n'.join(str(m.content) for m in assemble_system_messages(user_text='生成 Word', long_term=SimpleNamespace()))
        assert '<preloaded_skill' not in text
    finally:
        app_task_scope.reset(token)
    store.upsert(response.json()['task_id'], 'DONE')
    skills['app:cn.test.one:risk-analysis'].available = False
    invalid = await client.post('/api/industry-ai/cn.test.one/tasks', json=body(request_id='disabled', skills=['risk-analysis']))
    assert invalid.status_code == 403
    assert len(submitted) == 1


@pytest.mark.asyncio
async def test_real_graph_propagates_selected_resource_scope(tmp_path, monkeypatch):
    from app.graphs.single_agent import compile_single_agent_graph
    from app.observability.trace import TraceBus
    from app.orchestrator.task_manager import TaskManager, TaskRequest
    from tests.conftest import FakeChatModel, make_ai
    monkeypatch.setenv('MY_COWORK_DATA_DIR', str(tmp_path))
    _, skills = make_skills(tmp_path)
    key = 'app:cn.example.officecli:risk-analysis'
    class InspectModel(FakeChatModel):
        def _generate(self, messages, *args, **kwargs):
            context = '\n'.join(str(m.content) for m in messages)
            assert 'RISK RULE' in context and 'REPORT RULE' not in context
            if self.idx == 1:
                assert '1.0.0: evidence required' in context
            if self.idx == 2:
                assert '[ERROR]' in context
            return super()._generate(messages, *args, **kwargs)
    model = InspectModel(responses=[
        make_ai(tool_calls=[{'id': 'ref', 'name': 'read_skill_resource', 'args': {'name': key, 'path': 'references/rules.md'}}]),
        make_ai(tool_calls=[{'id': 'deny', 'name': 'read_skill_resource', 'args': {'name': 'app:cn.example.officecli:weekly-report', 'path': 'SKILL.md'}}]),
        make_ai('已根据证据完成风险分析。'),
    ])
    tools = make_skill_tools('single_agent', root=tmp_path/'user')
    graph = compile_single_agent_graph(model=model, tools=tools)
    manager = TaskManager(graph=graph, single_agent_graph=graph, tools=tools, bus=TraceBus())
    manager.app_skills = skills
    scope = AppTaskScope('cn.example.officecli', frozenset({'read_skill_resource'}), skills={key: skills[key]})
    events = [event async for event in manager.handle(TaskRequest(text='分析风险', task_id='skillgraph', session_mode='single-agent', memory_enabled=False, app_scope=scope))]
    assert events[-1]['status'] == 'ok', events[-1]
    assert model.idx == 3


def test_lifecycle_catalog_tracks_candidate_commit_rollback_disable(tmp_path):
    import hashlib
    import io
    import zipfile
    import yaml
    from fastapi import FastAPI
    from app.industry_apps.lifecycle import Maintenance
    from app.industry_apps.loader import load_enabled_apps
    from test_industry_lifecycle import bundle, activate, APP
    def packaged(version, *, fail=False):
        with zipfile.ZipFile(io.BytesIO(bundle(version, register="raise RuntimeError('bad register')" if fail else ''))) as archive:
            files = {name: archive.read(name) for name in archive.namelist() if name != 'checksums.sha256'}
        manifest = yaml.safe_load(files['mycowork-app.yaml'])
        manifest['skills'] = ['skills/risk-analysis']
        files['mycowork-app.yaml'] = yaml.safe_dump(manifest).encode()
        files['skills/risk-analysis/SKILL.md'] = f'---\nname: Risk\n---\nVersion {version}'.encode()
        files['skills/risk-analysis/references/rules.md'] = f'Reference {version}'.encode()
        files['checksums.sha256'] = ''.join(hashlib.sha256(value).hexdigest()+'  '+name+'\n' for name,value in files.items()).encode()
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w') as archive:
            for name, value in files.items():
                archive.writestr(name, value)
        return out.getvalue()
    def catalog():
        app = FastAPI()
        load_enabled_apps(app, tmp_path)
        return app.state.app_skills
    key = f'app:{APP}:risk-analysis'
    session = Maintenance(tmp_path)
    try:
        for version in ['1.0.0', '1.1.0']:
            raw = packaged(version)
            if version == '1.1.0':
                assert catalog()[key].app_origin['version'] == '1.0.0'
            session.begin('install', raw=raw, sha256=inspect_zip(raw).sha256)
            # The existing process keeps its loaded catalog until the controlled restart.
            with pytest.raises(RuntimeError, match='未完成操作'):
                catalog()
            activate(session)
            assert catalog()[key].app_origin['version'] == version
            from app.skills.bundled import read_skill_resource
            assert version in read_skill_resource(catalog()[key], 'references/rules.md')
        session.begin('rollback', APP)
        activate(session)
        assert '1.0.0' in catalog()[key].prompt
        session.begin('disable', APP)
        activate(session)
        disabled = catalog()
        assert not disabled[key].available
        with bundled_skill_scope(disabled):
            assert find_skill(key) is None
        session.begin('enable', APP)
        activate(session)
        assert catalog()[key].available
        bad = packaged('1.2.0', fail=True)
        session.begin('install', raw=bad, sha256=inspect_zip(bad).sha256)
        with pytest.raises(RuntimeError, match='load_failed'):
            activate(session)
        session.restore('load failed')
        session.commit()
        assert catalog()[key].app_origin['version'] == '1.0.0'
        session.begin('remove', APP)
        activate(session)
        assert not catalog()
    finally:
        session.close()


@pytest.mark.parametrize('path', ['../outside.md', '/absolute.md', 'C:/secret.txt', 'references/../SKILL.md', 'references\\rules.md'])
def test_resource_rejects_invalid_paths(tmp_path, path):
    from app.skills.bundled import read_skill_resource
    _, skills = make_skills(tmp_path)
    with pytest.raises(ValueError):
        read_skill_resource(next(iter(skills.values())), path)


def test_text_resources_reject_oversize_and_binary(tmp_path):
    from app.skills.bundled import read_skill_resource
    _, skills = make_skills(tmp_path)
    meta = next(iter(skills.values()))
    for name, content in [('big.md', b'x'*65537), ('binary.md', b'\xff'), ('script.py', b'print(1)')]:
        (meta.base_dir/name).write_bytes(content)
        with pytest.raises(ValueError):
            read_skill_resource(meta, name)
