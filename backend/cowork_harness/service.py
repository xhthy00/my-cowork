"""Run lifecycle around the official compiled graph; no self-managed act loop."""
import asyncio
import hashlib
import json
import time
from contextlib import AsyncExitStack
from pathlib import Path

import httpx
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from runtime_contract import RunRequest
from model_integrations.context import selection_key
from .agent_factory import build_agent
from .models import create_model
from .store import RunStore
from .upgrade_state import prepare_state
from .deliverables import preserve_html
from .events import DeltaBuffer


class SessionBusy(ValueError):
    """A new run must not take over another run's pending checkpoint."""


class BudgetCallback(AsyncCallbackHandler):
    raise_error = True

    def __init__(self, request, emit):
        self.request, self.emit = request, emit
        self.steps = self.tokens = self.input_tokens = self.output_tokens = 0
        self.prompts = {}
        self.contexts = {}

    async def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        # Fallback is a routing wrapper; its child callbacks count real attempts.
        if serialized.get('name') == 'FallbackChatModel':
            return
        limit = self.request.max_total_tokens
        step_limit = self.request.max_steps
        if step_limit is not None and self.steps >= step_limit:
            raise RuntimeError(f"已达到显式配置的模型调用上限（{step_limit} 次），任务已停止")
        if limit is not None and self.tokens >= limit:
            raise RuntimeError("Token budget exhausted")
        self.steps += 1
        prompt = count_tokens_approximately([m for group in messages for m in group],
            tools=(kwargs.get('invocation_params') or {}).get('tools'))
        self.prompts[str(run_id)] = prompt
        metadata = kwargs.get('metadata') or {}
        capacity = metadata.get('cowork_context_limit')
        namespace = metadata.get('langgraph_checkpoint_ns', '')
        is_root = '|' not in namespace and metadata.get('lc_source') != 'summarization'
        self.contexts[str(run_id)] = {
            'context_limit': capacity if isinstance(capacity, int) and capacity > 0 else None,
            'context_model': metadata.get('ls_model_name', ''),
            # The origin selection stays stable when an actual fallback model runs.
            'context_key': selection_key(self.request.models.get('supervisor', {})),
        } if is_root else None
        if limit is not None and self.tokens + sum(self.prompts.values()) > limit:
            raise RuntimeError("Token budget exhausted before model request")

    async def on_llm_end(self, response, *, run_id, **kwargs):
        if str(run_id) not in self.prompts:
            return
        usage = {}
        for group in response.generations:
            for generation in group:
                usage = getattr(getattr(generation, "message", None), "usage_metadata", None) or usage
        prompt_estimate = self.prompts.pop(str(run_id), 0)
        context = self.contexts.pop(str(run_id), None)
        context_fields = {**context, 'context_tokens': usage.get('input_tokens', prompt_estimate),
            'context_estimated': 'input_tokens' not in usage} if context is not None else {}
        output_estimate = sum(
            max(1, len(str(getattr(g, "text", ""))) // 3) for group in response.generations for g in group)
        self.input_tokens += int(usage.get("input_tokens") or prompt_estimate)
        self.output_tokens += int(usage.get("output_tokens") or output_estimate)
        self.tokens += int(usage.get("total_tokens") or prompt_estimate + output_estimate)
        self.emit({"type": "budget.update", "tokens": self.tokens, "steps": self.steps,
                   "max_steps": self.request.max_steps,
                   "max_tokens": self.request.max_total_tokens, "estimated": not bool(usage),
                   "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                   **context_fields})
        if self.request.max_total_tokens is not None and self.tokens > self.request.max_total_tokens:
            raise RuntimeError("Token budget exhausted")

    async def on_llm_error(self, error, *, run_id, **kwargs):
        self.prompts.pop(str(run_id), None)
        self.contexts.pop(str(run_id), None)


class RuntimeService:
    def __init__(self, data_dir, *, host_url="", host_token="", model_factory=None, call_host=None):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        prepare_state(self.data_dir.resolve())
        self.store = RunStore(self.data_dir / "runs.db")
        self.host_url, self.host_token = host_url, host_token
        self.model_factory = model_factory or create_model
        self.host_call_override = call_host
        self.tasks = {}
        self._stack = AsyncExitStack()
        self.saver = None
        self.draining = False
        self.session_locks = {}

    async def start(self):
        import os, sys
        def debug(stage):
            if os.environ.get('MY_COWORK_HARNESS_DEBUG') == '1':
                print('Harness service: ' + stage, file=sys.stderr, flush=True)
        debug('opening sqlite saver')
        self.saver = await self._stack.enter_async_context(
            AsyncSqliteSaver.from_conn_string(str(self.data_dir / "checkpoints.db")))
        await self.saver.setup()
        debug('sqlite saver ready')
        self.http = await self._stack.enter_async_context(httpx.AsyncClient(
            base_url=self.host_url or "http://127.0.0.1", trust_env=False, timeout=None,
            headers={"Authorization": "Bearer " + self.host_token}))
        debug("HTTP client ready")

    def profile(self, request):
        data = request.model_dump(exclude={"text", "history", "task_id", "session_id", "scope_ref",
                                          "workspace", "instructions", "resume_execution", "max_steps", "max_total_tokens", "planning_required"})
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    async def submit(self, request: RunRequest):
        if self.draining:
            raise ValueError("Runtime is draining")
        row, created = self.store.create(request.model_dump(), self.profile(request))
        if created:
            self.tasks[request.task_id] = asyncio.create_task(self._run(request.task_id))
        return {"run_id": row["id"], "status": row["status"], "created": created}

    async def _call_host(self, request, op, invocation_id, tool, args, **kwargs):
        if self.host_call_override:
            return await self.host_call_override(op, invocation_id, tool, args, scope_ref=request.scope_ref, **kwargs)
        result = await self.http.post(f"/{op}", json={"scope_ref": request.scope_ref,
            "invocation_id": invocation_id, "tool": tool, "args": args, **kwargs})
        result.raise_for_status()
        return result.json()

    def emit(self, run_id, event):
        # Resuming an interrupt re-enters the tool node; avoid duplicate starts.
        if event.get("call_id") and event["type"] == "tool.start":
            if self.store.has_tool_start(run_id, event['call_id']):
                return
        self.store.event(run_id, event)

    async def _run(self, run_id, resume=None):
        row = self.store.get(run_id)
        request = RunRequest.model_validate(row["request"])
        lock = self.session_locks.setdefault(row["thread_id"], asyncio.Lock())
        async with lock:
            self.store.update(run_id, "running")
            prior_plans = [e for e in self.store.events(run_id) if e['type'] == 'todo_state']
            plan_ready = not request.planning_required or bool(prior_plans and prior_plans[-1].get('todos'))
            writer = DeltaBuffer(lambda event: self.emit(run_id, event))
            def emit(event):
                nonlocal plan_ready
                if event['type'] == 'todo_state':
                    plan_ready = not request.planning_required or bool(event.get('todos'))
                name = event.get('tool')
                spec = next((spec for spec in request.tools if spec.name == name), None)
                if spec:
                    event = {**spec.metadata, **event}
                writer.emit(event)
            call_host = lambda op, cid, name, args, **kw: self._call_host(request, op, cid, name, args, **kw)
            budget = BudgetCallback(request, emit)
            usage = [event for event in self.store.events(run_id) if event['type'] == 'budget.update']
            if usage:
                budget.tokens, budget.steps = usage[-1]['tokens'], usage[-1]['steps']
                budget.input_tokens = usage[-1].get('input_tokens', 0)
                budget.output_tokens = usage[-1].get('output_tokens', 0)
            config = {"configurable": {"thread_id": row["thread_id"]}, "callbacks": [budget]}
            if request.max_steps is not None:
                config['recursion_limit'] = request.max_steps * 4 + 20
            try:
                agent = build_agent(request, self.saver, self.model_factory, call_host, emit)
                snapshot = await agent.aget_state(config)
                if resume is None:
                    if snapshot.next:
                        raise SessionBusy("此会话仍有挂起任务，请先恢复或取消")
                    messages = []
                    if not snapshot.values.get("messages"):
                        for turn in request.history:
                            if turn.get("role") in {"human", "user"}:
                                messages.append(HumanMessage(content=turn["content"]))
                            elif turn.get("role") in {"assistant", "ai"}:
                                messages.append(AIMessage(content=turn["content"]))
                    messages.append(HumanMessage(content=request.text))
                    value = {"messages": messages}
                    emit({"type": "graph.start"})
                    root_role = 'coordinator' if request.mode == 'workforce' else 'single_agent'
                    emit({'type': 'agent.create', 'agent_id': root_role, 'agent_type': root_role, 'name': root_role})
                    emit({'type': 'agent.activate', 'agent_id': root_role})
                else:
                    value = Command(resume=resume)
                final_text = ""
                async for chunk in agent.astream(value, config=config, stream_mode=["messages", "updates"],
                                                  subgraphs=True, version="v2"):
                    if chunk["type"] == "messages":
                        msg, metadata = chunk["data"]
                        text = text_content(msg.content)
                        if (plan_ready and text and not chunk.get("ns") and isinstance(msg, AIMessage)
                                and metadata.get('langgraph_node') == 'model'):
                            emit({"type": "step.delta", "delta": text})
                    elif chunk["type"] == "updates":
                        for update in chunk["data"].values():
                            if not isinstance(update, dict):
                                continue
                            if "todos" in update and not chunk.get("ns"):
                                emit({"type": "todo_state", "agent_id": "coordinator" if request.mode == "workforce" else "single_agent",
                                      "todos": [{**todo, "id": f"todo_{i + 1}",
                                                 "status": todo["status"]}
                                                for i, todo in enumerate(update["todos"])]})
                            for msg in update.get("messages", []):
                                if isinstance(msg, AIMessage) and not msg.tool_calls and not chunk.get("ns"):
                                    final_text = text_content(msg.content) or final_text
                snapshot = await agent.aget_state(config)
                if snapshot.interrupts:
                    pending = [{"interrupt_id": item.id, **item.value} for item in snapshot.interrupts]
                    self.store.update(run_id, "waiting_user", pending)
                    for item in pending:
                        kind = item["kind"]
                        if kind == "approval":
                            item['tool_title'] = next((spec.description.splitlines()[0][:80] for spec in request.tools
                                                       if spec.name == item['tool']), item['tool'])
                            emit({"type": "tool.confirm_request", **item})
                        elif kind == "human":
                            emit({"type": "human.ask", "question_id": item["interrupt_id"], **item})
                        else:
                            emit({"type": "to_sub_tasks", "needs_confirm": True, **item})
                    return
                if not final_text:
                    for msg in reversed(snapshot.values.get("messages", [])):
                        if isinstance(msg, AIMessage) and not msg.tool_calls:
                            final_text = text_content(msg.content)
                            if final_text:
                                break
                if not final_text:
                    raise RuntimeError("Agent completed without a final response")
                final_text = preserve_html(snapshot.values.get('messages', []), final_text)
                self.store.update(run_id, "succeeded")
                emit({"type": "graph.end", "status": "ok", "summary": final_text})
            except asyncio.CancelledError:
                try:
                    writer.flush()
                except Exception:
                    pass
                writer.discard()
                self.store.update(run_id, "cancelled")
                self.store.discard_epoch(row['thread_id'])
                self.emit(run_id, {"type": "graph.end", "status": "cancelled"})
            except Exception as exc:
                writer.discard()
                self.store.update(run_id, "failed")
                if not isinstance(exc, SessionBusy):
                    self.store.discard_epoch(row['thread_id'])
                self.emit(run_id, {"type": "graph.end", "status": "error", "error": str(exc)})
            finally:
                writer.close()

    async def resume(self, run_id, interrupt_id, value):
        row = self.store.get(run_id)
        if row is None or row["status"] != "waiting_user":
            raise ValueError("运行已不在等待输入")
        pending = list(row["pending"] or [])
        item = next((item for item in pending if item["interrupt_id"] == interrupt_id), None)
        if item is None:
            raise ValueError("中断标识已过期")
        if 'response' in item:
            raise ValueError('此中断已收到答复')
        if not isinstance(value, dict):
            raise ValueError('回复必须是结构化对象')
        if item['kind'] == 'approval' and not isinstance(value.get('ok'), bool):
            raise ValueError('审批需要明确的同意或拒绝')
        if item['kind'] == 'human' and not str(value.get('answer') or '').strip():
            raise ValueError('用户答复不能为空')
        if item['kind'] == 'plan' and (not isinstance(value.get('subtasks'), list) or
            any(not isinstance(task, dict) or not str(task.get('content') or '').strip() for task in value['subtasks'])):
            raise ValueError('计划需要有效的子任务列表')
        # Persist independent parallel interrupt replies until all are resolved.
        item["response"] = value
        self.store.update(run_id, "waiting_user", pending)
        if item['kind'] == 'human':
            self.emit(run_id, {'type': 'human.answered', 'question_id': interrupt_id, 'answer': value['answer']})
        elif item['kind'] == 'approval':
            self.emit(run_id, {'type': 'tool.confirm_resolved', 'call_id': item['call_id'], 'ok': value['ok']})
        if all("response" in item for item in pending):
            self.store.update(run_id, "queued")
            self.tasks[run_id] = asyncio.create_task(self._run(run_id,
                {item["interrupt_id"]: item["response"] for item in pending}))
        return {"ok": True}

    async def cancel(self, run_id):
        row = self.store.get(run_id)
        if not row or row["status"] in {"succeeded", "cancelled", "failed", "interrupted"}:
            return False
        task = self.tasks.get(run_id)
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if self.store.get(run_id)["status"] not in {"cancelled", "succeeded", "failed", "interrupted"}:
            self.store.update(run_id, "cancelled")
            self.emit(run_id, {"type": "graph.end", "status": "cancelled"})
        # A cancelled interrupt cannot be reused as the next turn's checkpoint.
        # Start subsequent conversation turns in a fresh epoch instead.
        self.store.discard_epoch(row['thread_id'])
        return True

    async def close(self):
        self.draining = True
        for task in self.tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        await self._stack.aclose()
        self.store.close()


def text_content(content):
    if isinstance(content, str):
        return content
    return "".join(block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text")
