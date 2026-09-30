"""Validate ZIP-contributed tools and adapt them to the Agent tool runtime."""

from __future__ import annotations

import asyncio
import inspect
import uuid
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from app.guardrails.approval import is_remote_channel
from app.industry_apps.package import AppManifest
from app.industry_apps.sdk import AppContribution, AppToolCallContext, LoadedAppTool
from app.runtime.todo_context import get_todo_runtime
from app.runtime.workspace_context import get_workspace_runtime
from app.task_support.admission import Admission
from app.task_support.app_context import app_task_scope


def validate_app_tools(manifest: AppManifest, contribution: AppContribution) -> list[LoadedAppTool]:
    """Require the loaded Python tools to match the reviewed ZIP manifest."""
    declared = {item.name: item for item in manifest.agent_tools}
    supplied = contribution.tools
    if len(supplied) != len(declared):
        raise ValueError("agent tools do not match the package manifest")
    loaded: list[LoadedAppTool] = []
    seen: set[str] = set()
    for tool in supplied:
        name = getattr(tool, "name", None)
        if not isinstance(name, str) or name in seen or name not in declared:
            raise ValueError("agent tools do not match the package manifest")
        seen.add(name)
        item = declared[name]
        if (tool.title != item.title or tool.description != item.description
                or tool.access != item.access):
            raise ValueError(f"agent tool {name!r} differs from the package manifest")
        if not isinstance(tool.args_schema, type) or not issubclass(tool.args_schema, BaseModel):
            raise TypeError(f"agent tool {name!r} needs a Pydantic args_schema")
        if not callable(tool.run):
            raise TypeError(f"agent tool {name!r} needs a callable run handler")
        loaded.append(LoadedAppTool(manifest.id, manifest.name, tool))
    return loaded


def agent_tool_name(entry: LoadedAppTool) -> str:
    return f"industry__{entry.app_id.replace('.', '_')}__{entry.tool.name}"


def agent_tool_metadata(entry: LoadedAppTool) -> dict[str, str]:
    return {
        "tool_source": "industry_app",
        "app_id": entry.app_id,
        "app_name": entry.app_name,
        "tool_title": entry.tool.title,
        "tool_access": entry.tool.access,
    }


def _call_context(app_id: str) -> AppToolCallContext:
    scope = app_task_scope.get()
    if scope and scope.app_id != app_id:
        raise PermissionError('Task belongs to another application')
    workspace = get_workspace_runtime()
    todo = get_todo_runtime()
    return AppToolCallContext(
        app_id=app_id,
        space_id=workspace.space_id if workspace else None,
        project_id=workspace.project_id if workspace else None,
        task_id=todo.task_id if todo else None,
        business=scope.business if scope else None,
    )


def make_agent_tool(entry: LoadedAppTool, confirm_hub: Any, admission: Admission | None = None) -> StructuredTool:
    """Wrap one app operation with typed arguments and a host write gate."""
    spec = entry.tool
    name = agent_tool_name(entry)
    metadata = agent_tool_metadata(entry)
    gate = admission or Admission()

    def run_sync(**kwargs: Any) -> Any:
        scope = app_task_scope.get()
        if scope and name not in scope.tools:
            raise PermissionError('Tool is outside the task scope')
        if spec.access == "write":
            raise RuntimeError("write tools require an asynchronous confirmation")
        args = spec.args_schema.model_validate(kwargs)
        with gate.work("插件工具"):
            result = spec.run(_call_context(entry.app_id), args)
            if inspect.isawaitable(result):
                return asyncio.run(result)
            return result

    async def run_async(**kwargs: Any) -> Any:
        scope = app_task_scope.get()
        if scope and name not in scope.tools:
            raise PermissionError('Tool is outside the task scope')
        args = spec.args_schema.model_validate(kwargs)
        if spec.access == "write":
            if is_remote_channel():
                return "[ERROR] Industry application writes require desktop approval"
            if confirm_hub is None:
                return "[ERROR] Host confirmation is unavailable"
            allowed = await confirm_hub.request(
                f"{name}:{uuid.uuid4().hex}", name,
                {**args.model_dump(mode="json"), **({'业务范围': scope.business} if scope else {})},
                tool_title=spec.title,
            )
            if not allowed:
                return "Operation rejected by user"
        context = _call_context(entry.app_id)
        operation_id = uuid.uuid4().hex
        def record(status, **details):
            if scope and scope.record_operation and spec.access == 'write':
                scope.record_operation({'type': 'app.operation', 'operation_id': operation_id,
                                        'tool': spec.title, 'status': status, **details})
        record('started', args=args.model_dump(mode='json'))
        if inspect.iscoroutinefunction(spec.run):
            with gate.work("插件工具"):
                try:
                    result = await spec.run(context, args)
                    record('completed', result=result)
                    return result
                except BaseException as exc:
                    record('interrupted' if isinstance(exc, asyncio.CancelledError) else 'failed', error=str(exc))
                    raise
        def execute():
            try:
                result = spec.run(context, args)
                record('completed', result=result)
                return result
            except BaseException as exc:
                record('failed', error=str(exc))
                raise
        return await gate.thread(execute)

    return StructuredTool.from_function(
        func=run_sync,
        coroutine=run_async,
        name=name,
        description=f"[行业工作台：{entry.app_name}] {spec.description}",
        args_schema=spec.args_schema,
        metadata=metadata,
    )
