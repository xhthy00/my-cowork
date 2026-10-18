"""Product task lifecycle; all cognition is delegated to Deep Agents."""
from __future__ import annotations
import asyncio
import contextvars
import hashlib
import json
import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, AsyncIterator
from contextlib import ExitStack

from runtime_contract import RunRequest, ToolSpec
from app.runtime.admission import Admission
from app.skills import find_skill
from app.runtime.app_context import AppTaskScope, app_task_scope, scoped_tools
from app.guardrails.approval import REMOTE_CHANNEL_SOURCES, set_remote_channel, reset_remote_channel


def _assistant_skill_prefix(
    assistant_id: str | None, skill_ids: list[str] | None
) -> str:
    """Prepend assistant rules + enabled skill bodies so the agent does not skip load_skill."""
    from app.assistants import get_assistant

    ids = [s for s in (skill_ids or []) if s]
    if not ids and not assistant_id:
        return ""
    blocks: list[str] = []
    if assistant_id:
        blocks.append(f"[assistant:{assistant_id}]")
        assistant = get_assistant(assistant_id)
        rules = str((assistant or {}).get("rules") or "").strip()
        if rules:
            blocks.append(
                f'<assistant_rules id="{assistant_id}">\n{rules}\n</assistant_rules>'
            )
    for sid in ids:
        meta = find_skill(sid)
        if meta is None or not meta.prompt:
            blocks.append(f"[skill:{sid} — not found on disk]")
            continue
        # Cap each skill to keep context bounded.
        body = meta.prompt.strip()
        if len(body) > 12000:
            body = body[:12000] + "\n…(truncated)"
        blocks.append(f"<preloaded_skill name=\"{sid}\">\n{body}\n</preloaded_skill>")
    if not blocks:
        return ""
    return (
        "The following assistant skills are preloaded for this task. "
        "Follow them; you may still call load_skill for extras.\n\n"
        + "\n\n".join(blocks)
        + "\n\n---\nUser request:\n"
    )


@dataclass
class TaskRequest:
    """Inbound request to run a task."""

    text: str
    task_id: str | None = None
    source: str = "user"
    reply_chat_id: str | None = None
    session_mode: str = "workforce"
    memory_enabled: bool = True
    enabled_mcp: list[str] | None = None
    history: list[dict[str, Any]] | None = None
    space_id: str | None = None
    project_id: str | None = None
    space_root_path: str | None = None
    workdir_mode: str | None = None
    assistant_id: str | None = None
    enabled_skill_ids: list[str] | None = None
    knowledge_bases: list[dict[str, Any]] | None = None
    session_id: str | None = None
    resume_execution: bool = False
    run_started_at: float | None = None
    automation_run_id: str | None = None
    automation_store: Any = None
    app_scope: AppTaskScope | None = None


class TaskManager:
    uses_deepagents = True
    def __init__(self, *, runtime, broker, tools, bus, models, role_tools=None,
                 data_dir=None, long_term=None, metrics=None, max_steps=None,
                 max_total_tokens=None, confirm_hub=None, human_input_hub=None,
                 task_store=None, short_term=None, admission=None, automation_store=None, **kwargs):
        self.runtime, self.broker, self.tools, self.bus = runtime, broker, tools, bus
        self.models, self.role_tools = models, role_tools or {}
        self.data_dir = Path(data_dir)
        self.long_term, self.metrics = long_term, metrics
        self.max_steps, self.max_total_tokens = max_steps, max_total_tokens
        self.confirm_hub, self.human_input_hub = confirm_hub, human_input_hub
        self.task_store, self.short_term = task_store, short_term
        self.admission = admission or Admission()
        self.automation_store = automation_store
        self.app_skills = {}
        self._tasks, self._workers, self._requests, self._scope_refs = {}, {}, {}, {}
        self._unsubscribe = self.bus.subscribe(self._on_host_event)
        if task_store and hasattr(task_store, 'interrupt_app_tasks'):
            task_store.interrupt_app_tasks()

    def _set_status(self, task_id, status, *, source=None, text=None):
        req = self._requests.get(task_id)
        source = source if source is not None else (req.source if req else 'user')
        text = text if text is not None else (req.text if req else '')
        self._tasks.setdefault(task_id, {'events': []})['status'] = status
        if self.task_store:
            try:
                self.task_store.upsert(task_id, status, source=source, text=text)
            except Exception as exc:
                self._tasks[task_id]['storage_error'] = str(exc)
                raise

    def status(self, task_id):
        if task_id in self._tasks:
            return self._tasks[task_id]['status']
        if self.task_store:
            status = self.task_store.get_status(task_id)
            if status:
                return status
        raise KeyError(task_id)

    async def submit(self, task_req):
        task_id = task_req.task_id or str(uuid.uuid4())
        fields = [key for key in task_req.__dataclass_fields__ if key not in
                  {'task_id', 'automation_store', 'app_scope', 'resume_execution', 'run_started_at'}]
        if task_id in self._workers:
            prior = self._requests[task_id]
            if any(getattr(prior, key) != getattr(task_req, key) for key in fields) or prior.app_scope != task_req.app_scope:
                raise ValueError('同一 task_id 不能用于不同请求')
            return task_id
        saved = self.broker.saved_request(task_id)
        if saved:
            if any(saved.get(key) != getattr(task_req, key) for key in fields):
                raise ValueError('同一 task_id 不能用于不同请求')
            try:
                row = await self.runtime.read(task_id)
            except Exception as exc:
                # Only a known missing run is safe to submit for the first time.
                if getattr(getattr(exc, 'response', None), 'status_code', None) != 404:
                    raise
                row = None
            if row:
                if row['status'] == 'waiting_user':
                    raise ValueError('任务正在等待输入，请恢复原任务')
                events = await self.runtime.history(task_id)
                self._requests[task_id] = replace(task_req, task_id=task_id)
                self._tasks[task_id] = {'events': events, 'status': {
                    'succeeded': 'DONE', 'cancelled': 'CANCELLED'}.get(row['status'], 'FAILED')}
                self._workers[task_id] = asyncio.create_task(asyncio.sleep(0))
                return task_id
        lease = self.admission.acquire(task_req.text[:60] or '聊天任务')
        task_req = replace(task_req, task_id=task_id)
        self._requests[task_id] = task_req
        try:
            self._set_status(task_id, 'NEW', source=task_req.source, text=task_req.text)
            self._workers[task_id] = asyncio.create_task(self._execute(task_req, lease))
            self._workers[task_id].add_done_callback(lambda _: self.admission.release(lease))
        except BaseException:
            self.admission.release(lease)
            raise
        return task_id

    async def handle(self, task_req) -> AsyncIterator[dict]:
        task_id = await self.submit(task_req)
        cursor = 0
        while True:
            rows = self._tasks[task_id]['events']
            while cursor < len(rows):
                event = rows[cursor]
                cursor += 1
                yield event
                if event['type'] == 'graph.end':
                    return
            # Closing a browser stream does not cancel the durable run.
            await asyncio.sleep(0.01)

    def cancel(self, task_id):
        if task_id not in self._workers or self._workers[task_id].done():
            return False
        if self._tasks[task_id]["status"] == "NEW":
            self._workers[task_id].cancel()
            self._record(task_id, {"type": "graph.end", "task_id": task_id, "status": "cancelled"})
            return True
        async def cancel_run():
            if not await self.runtime.cancel(task_id):
                return
            ref = self._scope_refs.get(task_id)
            if ref:
                await self.broker.cancel_scope(ref)
            self._workers[task_id].cancel()
        asyncio.create_task(cancel_run())
        return True

    def cancel_all(self):
        return sum(self.cancel(task_id) for task_id in list(self._workers))

    async def _prepare(self, req, scope_ref=None):
        from app.workspace.resolver import get_workspace_resolver
        from app.runtime.workspace_context import WorkspaceRuntime, set_workspace_runtime, reset_workspace_runtime
        from app.runtime.todo_context import TodoRuntime, set_todo_runtime, reset_todo_runtime
        from app.runtime.notes_context import NotesRuntime, set_notes_runtime, reset_notes_runtime
        from app.runtime.memory_context import set_long_term_runtime, reset_long_term_runtime
        from app.runtime.attachments import stage_attachments_for_task
        from app.runtime.v2.session import load_thread
        from app.skills import bundled_skill_scope, discover_skills
        from app.skills.config import load_skills_config, merge_skill_view, skill_visible_for_agent
        from app.assistants import get_assistant
        from app.tools.builtin.fs import get_guard
        from app.tools.mcp.manager import filter_mcp_tools, set_enabled_mcp, reset_enabled_mcp
        frozen = get_workspace_resolver().freeze_task_directories(
            space_id=req.space_id or 'space-local', project_id=req.project_id or req.session_id or req.task_id,
            task_id=req.task_id, space_root_path=req.space_root_path, workdir_mode=req.workdir_mode)
        guard = get_guard()
        guard.add_whitelist(str(frozen.working_directory))
        guard.add_whitelist(str(frozen.task_output_root))
        if frozen.space_root:
            guard.add_whitelist(str(frozen.space_root))
        text = stage_attachments_for_task(req.text, frozen.working_directory, guard)
        role = 'single_agent' if req.session_mode == 'single-agent' else 'coordinator'
        todo = TodoRuntime(task_id=req.task_id, bus=self.bus, agent_id=role, user_text=req.text,
            source=req.source, workspace=str(frozen.working_directory), project_id=req.project_id,
            space_id=req.space_id, memory_root=req.space_root_path, session_id=req.session_id or req.project_id or req.task_id,
            assistant_id=req.assistant_id, automation_run_id=req.automation_run_id, automation_store=req.automation_store)
        with ExitStack() as stack:
            if req.source == 'schedule' and req.automation_run_id and self.automation_store:
                from app.guardrails.approval import set_automation_policy, reset_automation_policy
                run = self.automation_store.get_run(req.automation_run_id)
                automation = self.automation_store.get(run.task_id) if run else None
                if automation is None:
                    raise ValueError('定时任务已删除，不能恢复其权限')
                todo.automation_store = self.automation_store
                current = lambda: self.automation_store.get(automation.id)
                token = set_automation_policy(automation.workspace, automation.always_allowed_tools,
                    current_grants=lambda: current().always_allowed_tools if current() else [],
                    commands=automation.always_allowed_commands,
                    current_commands=lambda: current().always_allowed_commands if current() else [],
                    auto_approve_commands=automation.auto_approve_commands,
                    current_auto_approve_commands=lambda: bool(current() and current().auto_approve_commands))
                stack.callback(reset_automation_policy, token)
            for setter, resetter, value in (
                (app_task_scope.set, app_task_scope.reset, req.app_scope),
                (set_remote_channel, reset_remote_channel, req.source in REMOTE_CHANNEL_SOURCES),
                (set_enabled_mcp, reset_enabled_mcp, req.enabled_mcp),
                (set_todo_runtime, reset_todo_runtime, todo),
                (set_notes_runtime, reset_notes_runtime, NotesRuntime(req.task_id, self.data_dir / 'notes')),
                (set_long_term_runtime, reset_long_term_runtime, self.long_term if req.memory_enabled else None),
                (set_workspace_runtime, reset_workspace_runtime, WorkspaceRuntime(
                    space_id=req.space_id or 'space-local', project_id=req.project_id or req.task_id,
                    task_id=req.task_id, working_directory=frozen.working_directory,
                    task_output_root=frozen.task_output_root, workdir_mode=frozen.workdir_mode,
                    base_snapshot_id=frozen.base_snapshot_id, space_root=frozen.space_root))):
                stack.callback(resetter, setter(value))
            stack.enter_context(bundled_skill_scope(self.app_skills,
                selected=req.app_scope.skills if req.app_scope else None))
            tools = filter_mcp_tools(scoped_tools(self.tools), req.enabled_mcp)
            tools = [tool for tool in tools if tool.name not in {'ask_human', 'todo_write', 'substep_update', 'list_skills', 'load_skill', 'read_skill_resource'}
                     and (req.memory_enabled or not tool.name.startswith('memory_'))]
            metadata = {key: getattr(req, key) for key in req.__dataclass_fields__
                        if key not in {'automation_store', 'app_scope'}}
            metadata['restorable'] = req.app_scope is None
            ref = self.broker.register(tools, contextvars.copy_context(), metadata=metadata, ref=scope_ref)
            self._scope_refs[req.task_id] = ref
            specs = [ToolSpec(name=tool.name, description=tool.description,
                input_schema=tool.args_schema if isinstance(tool.args_schema, dict) else tool.args_schema.model_json_schema(),
                roles=[role for role, names in self.role_tools.items() if tool.name in names],
                metadata=dict(tool.metadata or {})) for tool in tools]
            assistant = get_assistant(req.assistant_id) if req.assistant_id else {}
            selected = req.enabled_skill_ids if req.enabled_skill_ids is not None else (assistant or {}).get('enabled_skills')
            cfg = load_skills_config(os.environ.get('MY_COWORK_SKILLS_CONFIG'))
            skills, routes = {}, {}
            for skill in discover_skills(root=Path(os.environ['MY_COWORK_SKILLS_ROOT']) if os.environ.get('MY_COWORK_SKILLS_ROOT') else None, bundled=req.app_scope.skills if req.app_scope else self.app_skills):
                if selected is not None and skill.id not in selected:
                    continue
                view = merge_skill_view(skill, cfg)
                if not view['enabled']:
                    continue
                revision = hashlib.sha256(json.dumps([skill.id, skill.prompt, skill.description or skill.name], ensure_ascii=False).encode())
                items = sorted(skill.base_dir.rglob('*')) if skill.base_dir else []
                if any(item.is_symlink() for item in items):
                    raise ValueError(f'Skill contains links: {skill.id}')
                for item in items:
                    if item.is_file():
                        revision.update(str(item.relative_to(skill.base_dir)).encode())
                        with item.open('rb') as resource:
                            for chunk in iter(lambda: resource.read(1024 * 1024), b''):
                                revision.update(chunk)
                slug = revision.hexdigest()[:16]
                root = self.data_dir / 'harness-skills' / slug
                skill_name = re.sub('[^a-z0-9-]+', '-', skill.id.lower()).strip('-')[:40] + '-' + slug[:6]
                dest = root / skill_name
                if skill.base_dir and skill.base_dir.is_dir() and not (dest / 'SKILL.md').exists():
                    shutil.copytree(skill.base_dir, dest, dirs_exist_ok=True)
                else:
                    dest.mkdir(parents=True, exist_ok=True)
                # Normalize legacy skill.yaml packages to the official SKILL.md format.
                front = '---\nname: ' + json.dumps(skill_name, ensure_ascii=False) + '\ndescription: ' + json.dumps(skill.description or skill.name or skill.id, ensure_ascii=False) + '\n---\n'
                entry = dest / 'SKILL.md'
                content = front + skill.prompt
                if not entry.exists() or entry.read_text(encoding='utf-8') != content:
                    temporary = dest / ('.SKILL-' + uuid.uuid4().hex + '.tmp')
                    temporary.write_text(content, encoding='utf-8')
                    temporary.replace(entry)
                virtual = f'/skills/{slug}/'
                routes[virtual] = str(root)
                for role in ['supervisor', *self.role_tools]:
                    visible_role = 'single_agent' if role == 'supervisor' and req.session_mode == 'single-agent' else role
                    if skill_visible_for_agent(view, visible_role):
                        skills.setdefault(role, []).append(virtual)
            instructions = '用用户的语言回答，执行用户请求并验证结果。\n' + str((assistant or {}).get('rules') or '')
            instructions += f'\n真实工作目录：{frozen.working_directory}；read_file 使用 /workspace/ 虚拟路径，bash 和宿主工具使用真实路径。'
            if req.knowledge_bases:
                instructions += '\n绑定知识库：' + json.dumps(req.knowledge_bases, ensure_ascii=False)
            memory_paths = []
            settings = getattr(self.long_term, 'memory_settings', None)
            if req.memory_enabled and self.long_term is not None and (settings is None or settings.enabled):
                from app.memory.scoped import project_memory_key
                block = self.long_term.prompt_block(workspace=project_memory_key(req.space_root_path, req.project_id), session_id=todo.session_id)
                memory_id = hashlib.sha256((todo.session_id + block).encode()).hexdigest()[:16]
                memory_root = self.data_dir / 'harness-memory' / memory_id
                memory_root.mkdir(parents=True, exist_ok=True)
                (memory_root / 'AGENTS.md').write_text(block or '遵循本次用户请求。', encoding='utf-8')
                routes['/memories/'] = str(memory_root)
                memory_paths = ['/memories/AGENTS.md']
            history = req.history or [{'role': m.type, 'content': m.content}
                for m in load_thread(todo.session_id) if m.type in {'human', 'ai'} and not getattr(m, 'tool_calls', [])]
            return RunRequest(task_id=req.task_id, session_id=todo.session_id, text=text,
                mode=req.session_mode, scope_ref=ref, workspace=str(frozen.working_directory),
                workspace_key=json.dumps([req.space_id, req.project_id, req.space_root_path]),
                profile_revision=hashlib.sha256(json.dumps(assistant or {}, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                models=self.models, tools=specs, instructions=instructions, skills=skills, skill_routes=routes,
                history=history, memory_paths=memory_paths, file_access=req.app_scope is None,
                confirm_plan=req.source not in REMOTE_CHANNEL_SOURCES, max_steps=self.max_steps,
                max_total_tokens=self.max_total_tokens, resume_execution=req.resume_execution)

    async def recover(self):
        await self.runtime.start()
        for ref, metadata in self.broker.saved_scopes():
            restorable = metadata.pop('restorable', False)
            req = TaskRequest(**metadata)
            try:
                row = await self.runtime.read(req.task_id)
            except Exception:
                continue
            if not row:
                continue
            if not restorable:
                if row['status'] == 'waiting_user':
                    await self.runtime.cancel(req.task_id)
                continue
            if row['status'] == 'interrupted':
                self._requests[req.task_id] = req
                self._set_status(req.task_id, 'FAILED')
                for event in await self.runtime.history(req.task_id):
                    self._record(req.task_id, event, publish=False)
                continue
            if row['status'] != 'waiting_user':
                continue
            # Never silently resume an app task whose callbacks cannot survive
            # a host restart. Normal task scope is reconstructed from host data.
            self._requests[req.task_id] = req
            self._set_status(req.task_id, 'WAITING_USER')
            lease = self.admission.acquire(req.text[:60] or '恢复任务', restoring=True)
            prepared = asyncio.get_running_loop().create_future()
            self._workers[req.task_id] = asyncio.create_task(self._follow(req, lease, ref, prepared))
            self._workers[req.task_id].add_done_callback(lambda _, held=lease: self.admission.release(held))
            try:
                await prepared
            except Exception:
                # The observer records a durable failure if scope restoration fails.
                continue

    async def _follow(self, req, lease, ref, prepared):
        try:
            with self.admission.work(req.task_id, lease):
                await self._prepare(req, scope_ref=ref)
                prepared.set_result(True)
                row = await self.runtime.read(req.task_id)
                await self._consume(req, row.get('request') or {}, req.run_started_at or 0)
        except asyncio.CancelledError:
            if not prepared.done():
                prepared.cancel()
            raise
        except Exception as exc:
            if not prepared.done():
                prepared.set_exception(exc)
            await self._fail(req.task_id, exc)

    def _on_host_event(self, event):
        task_id = event.get('task_id')
        if task_id in self._tasks and not event.get('event_id') and event['type'] != 'graph.end':
            # _record publishes its own host events after persisting them.
            if any(row is event for row in self._tasks[task_id]['events']):
                return
            try:
                self._record(task_id, event, publish=False)
            except Exception as exc:
                self._tasks[task_id]['storage_error'] = str(exc)

    def _record(self, task_id, event, publish=True):
        state = self._tasks[task_id]
        if event.get('event_id') and any(row.get('event_id') == event['event_id'] for row in state['events']):
            return
        if event["type"] == "graph.end" and any(row["type"] == "graph.end" for row in state["events"]):
            return
        if self.task_store:
            self.task_store.append_event(task_id, event)
        state['events'].append(event)
        if publish:
            self.bus.emit(event)
        if event['type'] in {'tool.confirm_request', 'human.ask', 'to_sub_tasks'}:
            self._set_status(task_id, 'WAITING_USER')
        elif event['type'] in {'human.answered', 'tool.confirm_resolved', 'step.delta', 'tool.result'}:
            self._set_status(task_id, 'RUNNING')
        elif event['type'] == 'graph.end':
            self._set_status(task_id, {'ok': 'DONE', 'cancelled': 'CANCELLED'}.get(event.get('status'), 'FAILED'))

    async def _execute(self, req, lease):
        started = req.run_started_at or time.time()
        req.run_started_at = started
        try:
            with self.admission.work(req.task_id, lease):
                self._set_status(req.task_id, 'RUNNING', source=req.source, text=req.text)
                request = await self._prepare(req)
                await self.runtime.submit(request)
                await self._consume(req, request.model_dump(), started)
        except asyncio.CancelledError:
            if self._tasks[req.task_id].get('status') != 'WAITING_USER':
                self._record(req.task_id, {'type': 'graph.end', 'task_id': req.task_id, 'status': 'cancelled'})
        except Exception as exc:
            await self._fail(req.task_id, exc)
        finally:
            self.admission.release(lease)

    async def _fail(self, task_id, exc):
        # Stop remote computation and host effects before reporting failure.
        await asyncio.gather(self.runtime.cancel(task_id),
            self.broker.cancel_scope(self._scope_refs.get(task_id)), return_exceptions=True)
        state = self._tasks[task_id]
        state['storage_error'] = str(exc)
        event = {'type': 'graph.end', 'task_id': task_id, 'status': 'error', 'error': str(exc)}
        try:
            self._record(task_id, event)
        except Exception:
            state['events'].append(event)
            self.bus.emit(event)
        state['status'] = 'FAILED'
        try:
            self._set_status(task_id, 'FAILED')
        except Exception:
            pass

    async def _consume(self, req, request, started):
        from app.tools.builtin.fs import get_guard
        from app.workspace.artifacts import paths_in_answer, paths_in_write_result, verified_artifact
        from app.workspace.output_files import list_new_output_files
        workspace = request.get('workspace', '')
        seen = {row.get('path') for row in self._tasks[req.task_id]['events'] if row['type'] == 'artifact.file'}

        def register(paths):
            for raw in paths:
                path = verified_artifact(raw, workspace, get_guard(), req.app_scope)
                if path and path not in seen:
                    self._record(req.task_id, {'type': 'artifact.file', 'task_id': req.task_id, 'path': path})
                    seen.add(path)

        async for event in self.runtime.events(req.task_id):
            if event['type'] == 'graph.end' and event.get('status') != 'ok':
                await self.broker.cancel_scope(self._scope_refs.get(req.task_id))
            if event['type'] == 'graph.end' and self.metrics:
                usage = [row for row in self._tasks[req.task_id]['events'] if row['type'] == 'budget.update']
                if usage:
                    last = usage[-1]
                    self.metrics.log(req.task_id, tokens_in=last.get('input_tokens', last['tokens']),
                        tokens_out=last.get('output_tokens', 0), usd=last['tokens'] * 1e-6)
                    self.metrics.check_daily_threshold(float(os.environ.get('MY_COWORK_DAILY_USD', '10')), self.bus)
            if self._tasks[req.task_id].get('storage_error'):
                raise OSError(self._tasks[req.task_id]['storage_error'])
            if event['type'] == 'tool.result' and event.get('tool') in {'fs_write', 'fs.write', 'docx_gen', 'pptx_gen', 'xlsx_gen', 'pdf_gen', 'app_write_report'}:
                register(paths_in_write_result(event.get('result', '')))
            if event['type'] == 'graph.end' and event.get('status') == 'ok':
                if started > 0:
                    register(await asyncio.to_thread(list_new_output_files, workspace, min_mtime=started))
                register(paths_in_answer(event.get('summary', '')))
                from app.runtime.v2.session import append_run
                from langchain_core.messages import HumanMessage, AIMessage
                append_run(request.get('session_id') or req.session_id or req.task_id, [HumanMessage(content=req.text), AIMessage(content=event.get('summary', ''))])
            self._record(req.task_id, event)

        if not any(event['type'] == 'graph.end' for event in self._tasks[req.task_id]['events']):
            raise RuntimeError('Harness 事件流在完成前中断')

    async def resolve(self, task_id, key, value):
        try:
            row = await self.runtime.read(task_id)
        except Exception as exc:
            if getattr(getattr(exc, 'response', None), 'status_code', None) == 404:
                return False
            raise
        if not row or row['status'] != 'waiting_user':
            return False
        item = next((item for item in (row.get('pending') or []) if key in {item['interrupt_id'], item.get('call_id')}), None)
        if item is None:
            return False
        if 'response' in item:
            return False
        if item['kind'] == 'approval':
            if not self.broker.approve(item['call_id'], value['ok']):
                return False
        await self.runtime.resume(task_id, item['interrupt_id'], value)
        return True

    async def pending(self, task_id):
        return (await self.runtime.read(task_id)).get('pending') or []

    async def close(self):
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None
        for task_id in self._workers:
            if not self._workers[task_id].done():
                ref = self._scope_refs.get(task_id)
                if ref:
                    await self.broker.cancel_scope(ref)
                self._workers[task_id].cancel()
        await asyncio.gather(*self._workers.values(), return_exceptions=True)
        await self.runtime.close()
        self.broker.close()
