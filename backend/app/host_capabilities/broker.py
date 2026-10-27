"""Scope-bound, durable tool tickets and idempotent invocation records."""
import asyncio
import contextvars
import hashlib
import json
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from runtime_contract import ToolInvocation
from jsonschema import ValidationError
from jsonschema.validators import validator_for
from app.guardrails.approval import _automation_policy, _automation_allows, is_remote_channel

runtime_confirmed = contextvars.ContextVar("runtime_confirmed", default=False)

READ_TOOLS = frozenset({"fs_read", "fs_list", "web_search", "web_fetch", "app_read_file",
    "read_note", "list_note", "conversation_read", "memory_search", "memory_read", "app_write_report",
    "browser_screenshot", "browser_get_tabs", "browser_get_state"})
APPROVAL_NAMES = {"fs_write": "fs.write", "bash": "exec.bash", "docx_gen": "docx.gen",
    "pptx_gen": "pptx.gen", "xlsx_gen": "xlsx.gen", "pdf_gen": "pdf.gen",
    "lark_send_message": "lark.send_message"}


class CapabilityBroker:
    def __init__(self, data_dir, bus):
        self.bus = bus
        self.scopes = {}
        self.running = {}
        self.db = sqlite3.connect(Path(data_dir) / "tool-invocations.db")
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE TABLE IF NOT EXISTS invocations (
            scope TEXT NOT NULL, id TEXT NOT NULL, fingerprint TEXT NOT NULL,
            ticket TEXT UNIQUE NOT NULL, state TEXT NOT NULL, result TEXT,
            PRIMARY KEY(scope,id))""")
        self.db.execute("UPDATE invocations SET state='unknown' WHERE state='started'")
        self.db.execute("CREATE TABLE IF NOT EXISTS scopes (ref TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        self.db.commit()

    def register(self, tools, context=None, *, metadata=None, ref=None):
        ref = ref or secrets.token_urlsafe(32)
        self.scopes[ref] = {"tools": {tool.name: tool for tool in tools},
                            "context": context or contextvars.copy_context()}
        if metadata is not None:
            self.db.execute("INSERT OR REPLACE INTO scopes VALUES (?, ?)",
                            (ref, json.dumps(metadata, ensure_ascii=False)))
            self.db.commit()
        return ref

    def saved_scopes(self):
        return [(row[0], json.loads(row[1])) for row in self.db.execute("SELECT ref, payload FROM scopes")]

    def saved_request(self, task_id):
        row = self.db.execute("SELECT payload FROM scopes WHERE json_extract(payload, '$.task_id')=? LIMIT 1",
                              (task_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def scope(self, body):
        scope = self.scopes.get(body.scope_ref)
        if scope is None or body.tool not in scope["tools"]:
            raise HTTPException(403, "工具不在当前任务授权范围内")
        return scope

    def fingerprint(self, body):
        return hashlib.sha256(json.dumps({"tool": body.tool, "args": body.args},
                             sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def decision(self, body, scope):
        def check():
            if body.tool in READ_TOOLS or (scope['tools'][body.tool].metadata or {}).get('tool_access') == 'read':
                return "allow"
            policy = _automation_policy.get()
            if policy is not None and _automation_allows(
                APPROVAL_NAMES.get(body.tool, body.tool), body.args, policy):
                return "allow"
            if policy is None and is_remote_channel():
                return "allow"
            return "ask"
        return scope["context"].run(check)

    async def authorize(self, body):
        scope = self.scope(body)
        tool = scope["tools"][body.tool]
        if (tool.metadata or {}).get("mcp_server"):
            schema = tool.args_schema
            try:
                validator_for(schema)(schema).validate(body.args)
            except ValidationError as exc:
                return {"decision": "deny", "error": "工具参数无效：" + exc.message}
        row = self.db.execute("SELECT * FROM invocations WHERE scope=? AND id=?",
                              (body.scope_ref, body.invocation_id)).fetchone()
        fingerprint = self.fingerprint(body)
        if row:
            if row["fingerprint"] != fingerprint:
                raise HTTPException(409, "工具调用标识与参数不一致")
            if row["state"] in {"unknown", "started"}:
                return {"decision": "deny", "error": "工具副作用状态未知，需要人工对账"}
            if row["state"] == "rejected":
                return {"decision": "deny", "error": "Operation rejected by user"}
            return {"decision": "allow" if row["state"] in {"authorized", "completed"} else "ask",
                    "ticket": row["ticket"]}
        decision = self.decision(body, scope)
        ticket = secrets.token_urlsafe(32)
        self.db.execute("INSERT INTO invocations VALUES (?, ?, ?, ?, ?, NULL)",
                        (body.scope_ref, body.invocation_id, fingerprint, ticket,
                         "authorized" if decision == "allow" else "waiting"))
        self.db.commit()
        return {"decision": decision, "ticket": ticket}

    def approve(self, ticket, ok):
        row = self.db.execute("SELECT state FROM invocations WHERE ticket=?", (ticket,)).fetchone()
        if row and row["state"] == ("authorized" if ok else "rejected"):
            return True
        cursor = self.db.execute("UPDATE invocations SET state=? WHERE ticket=? AND state='waiting'",
                                 ("authorized" if ok else "rejected", ticket))
        self.db.commit()
        return bool(cursor.rowcount)

    async def execute(self, body):
        self.bus.bind_loop()
        scope = self.scope(body)
        row = self.db.execute("SELECT * FROM invocations WHERE ticket=? AND scope=? AND id=?",
                              (body.ticket, body.scope_ref, body.invocation_id)).fetchone()
        if row is None or row["fingerprint"] != self.fingerprint(body):
            raise HTTPException(403, "工具授权凭据无效")
        if row["state"] == "completed":
            return json.loads(row["result"])
        if row["state"] != "authorized":
            raise HTTPException(409, "工具未批准或执行状态未知")
        self.db.execute("UPDATE invocations SET state='started' WHERE ticket=?", (body.ticket,))
        self.db.commit()
        async def invoke():
            token = runtime_confirmed.set(True)
            try:
                from app.runtime.todo_context import get_todo_runtime
                todo = get_todo_runtime()
                automation = getattr(todo, 'automation_store', None)
                run_id = getattr(todo, 'automation_run_id', None)
                if automation and run_id:
                    automation.tool_started(run_id, body.invocation_id, body.tool, todo.session_id)
                result = await scope["tools"][body.tool].ainvoke(body.args)
                if automation and run_id:
                    automation.tool_completed(run_id, body.invocation_id)
                return result
            finally:
                runtime_confirmed.reset(token)
        task = scope["context"].run(asyncio.create_task, invoke())
        self.running[(body.scope_ref, body.invocation_id)] = task
        try:
            result = await task
        except asyncio.CancelledError:
            self.db.execute("UPDATE invocations SET state='unknown' WHERE ticket=?", (body.ticket,))
            self.db.commit()
            raise
        except Exception as exc:
            self.db.execute("UPDATE invocations SET state='unknown' WHERE ticket=?", (body.ticket,))
            self.db.commit()
            return {'error': str(exc), 'execution_state': 'unknown',
                    'message': '工具抛出异常，副作用可能已发生，请对账后再重试'}
        finally:
            self.running.pop((body.scope_ref, body.invocation_id), None)
        self.db.execute("UPDATE invocations SET state='completed', result=? WHERE ticket=?",
                        (json.dumps(result, ensure_ascii=False, default=str), body.ticket))
        self.db.commit()
        return result

    async def cancel_scope(self, ref):
        for row in self.db.execute("SELECT id FROM invocations WHERE scope=? AND state='started'", (ref,)):
            task = self.running.get((ref, row[0]))
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    def app(self, token):
        app = FastAPI(docs_url=None, redoc_url=None)
        @app.middleware("http")
        async def authorize_request(request: Request, call_next):
            from starlette.responses import JSONResponse
            if request.headers.get("origin") or not secrets.compare_digest(
                request.headers.get("authorization", ""), "Bearer " + token):
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
            return await call_next(request)
        @app.post("/authorize")
        async def authorize_tool(body: ToolInvocation):
            return await self.authorize(body)
        @app.post("/execute")
        async def execute_tool(body: ToolInvocation):
            return await self.execute(body)
        return app

    def close(self):
        self.db.close()
