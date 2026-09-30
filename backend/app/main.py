"""Application assembly point.

This module is intentionally outside the harness layer contract. It is the
only place allowed to instantiate and wire the 9 layers together.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

_STARTUP_STARTED = time.perf_counter()


def _startup_stage(name: str) -> None:
    print(f"[startup] {name} ({time.perf_counter() - _STARTUP_STARTED:.2f}s)", file=sys.stderr, flush=True)


_startup_stage("loading modules")

# Child processes inherit these. Set before other imports that spawn tools.
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.platform == "win32":
    try:
        import ctypes

        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.language_models.chat_models import BaseChatModel

from app.graphs.single_agent import compile_single_agent_graph
from app.graphs.workforce import compile_workforce_graph
from app.guardrails.approval import ConfirmHub
from app.guardrails.human_input import HumanInputHub
from app.guardrails.audit import AuditStore
from app.guardrails.command_filter import CommandFilter
from app.llm import gateway, model_picker
from app.llm.fallback import FallbackChatModel
from app.memory.long_term import LongTermStore
from app.memory.settings import MemorySettings
from app.memory.tools import make_memory_tools
from app.memory.short_term import ShortTermStore
from app.observability.metrics import MetricsStore
from app.observability.trace import TraceBus
from app.observability.trace_store import TraceStore
from app.orchestrator.task_manager import TaskManager
from app.orchestrator.task_store import TaskStore
from app.automation import AutomationScheduler, AutomationStore
from app.automation.migration import import_legacy_jobs, import_skill_schedules
from app.automation.runtime import AutomationRunner
from app.automation.tools import make_automation_tools
from app.runtime.checkpointer import get_checkpointer
from app.runtime.v2.context_tools import make_context_tools
from app.sandbox.path_guard import PathGuard
from app.workspace.paths import data_root
from app.server.localhost_only import LocalhostOnlyMiddleware
from app.server.industry_auth import IndustryAppAuthMiddleware
from app.server.channels.manager import ChannelManager
from app.server.channels.store import ChannelStore
from app.server.desktop_sessions import DesktopSessionStore
from app.server.routes import (
    audit as audit_routes,
    automations as automation_routes,
    browser as browser_routes,
    assistants as assistants_routes,
    channels as channels_routes,
    chat,
    desktop_sessions as desktop_sessions_routes,
    confirm,
    ima as ima_routes,
    industry_apps as industry_apps_routes,
    mcp as mcp_routes,
    memory as memory_routes,
    model as model_routes,
    officecli as officecli_routes,
    schedule as schedule_routes,
    skills as skills_routes,
    trace as trace_routes,
    webhook_lark,
    workspace as workspace_routes,
)
from app.industry_apps.loader import load_enabled_apps
from app.industry_apps.locks import FileLock
from app.industry_apps.package import app_root
from app.industry_apps.lifecycle import runtime_entries
from app.task_support.admission import Admission, MaintenanceBusy
from app.server.maintenance import AdmissionMiddleware, router as maintenance_router
from app.industry_apps.sdk import LoadedAppTool
from app.industry_apps.tooling import make_agent_tool
from app.tools.builtin import exec as exec_tool
from app.tools.builtin.docgen import pptx_gen
from app.tools.builtin.docgen.tools import (
    make_docx_tool,
    make_gongwen_format_tool,
    make_pdf_tool,
    make_pptx_tool,
    make_xlsx_tool,
)
from app.tools.builtin.fs import fs_list, fs_read, make_fs_write, set_guard
from app.tools.builtin.lark.tools import make_lark_send_tool
from app.tools.builtin.notes import make_note_tools
from app.tools.builtin.human import make_ask_human_tool
from app.tools.builtin.skills import make_skill_tools
from app.tools.builtin.todo import make_substep_update_tool, make_todo_write_tool
from app.tools.builtin.web_search import make_web_search_tool
from app.tools.builtin.web_fetch import make_web_fetch_tool
from app.tools.builtin.browser import make_browser_tools
from app.tools.builtin.ima.tools import make_ima_tools
from app.skills.config import default_skills_config_path, default_skills_root
from app.skills import default_example_skills_root, legacy_user_skills_roots
from app.tools.mcp.manager import (
    McpManager,
    default_mcp_json_path,
    load_mcp_json,
    mcp_json_to_configs,
    parse_mcp_servers,
    save_mcp_json,
)
from app.tools.registry import ToolRegistry


def _parse_fallback_specs() -> list[tuple[str, str]]:
    """Parse ``MY_COWORK_FALLBACK=provider:model;provider:model``."""
    raw = (os.environ.get("MY_COWORK_FALLBACK") or "").strip()
    if not raw:
        return []
    out: list[tuple[str, str]] = []
    for part in raw.split(";"):
        part = part.strip()
        if not part or ":" not in part:
            continue
        provider, model = part.split(":", 1)
        provider, model = provider.strip(), model.strip()
        if provider and model:
            out.append((provider, model))
    return out


def _default_model_factory(
    provider: str,
    model: str,
    *,
    emit: Any = None,
) -> BaseChatModel:
    """Create a real LangChain model from environment variables.

    Optional ``MY_COWORK_FALLBACK`` builds a ``FallbackChatModel`` chain.
    """
    api_key = os.environ.get("MY_COWORK_API_KEY")
    if not api_key:
        raise RuntimeError(
            "MY_COWORK_API_KEY is not set; cannot create the default LLM client."
        )

    def _one(p: str, m: str) -> BaseChatModel:
        from app.llm.budget_callback import instrument_model_for_budget

        kwargs: dict[str, Any] = {}
        base_url = os.environ.get("MY_COWORK_BASE_URL")
        if base_url and p == "openai_compat":
            kwargs["base_url"] = base_url
        return instrument_model_for_budget(
            gateway.create_model(p, m, api_key, **kwargs)
        )

    primary = _one(provider, model)
    specs = _parse_fallback_specs()
    if not specs:
        return primary

    chain = [primary]
    for p, m in specs:
        if (p, m) == (provider, model):
            continue
        try:
            chain.append(_one(p, m))
        except Exception:
            continue
    if len(chain) == 1:
        return primary

    def _on_fallback(idx: int, exc: BaseException) -> None:
        if emit is None:
            return
        try:
            emit(
                {
                    "type": "llm.fallback",
                    "from_index": idx,
                    "error": str(exc),
                }
            )
        except Exception:
            pass

    from app.llm.budget_callback import instrument_model_for_budget

    return instrument_model_for_budget(
        FallbackChatModel(chain, on_fallback=_on_fallback)
    )


def _resolve_llm(task_kind: str) -> tuple[str, str]:
    """Prefer Electron-injected active model; else fall back to model_picker."""
    provider = os.environ.get("MY_COWORK_PROVIDER")
    model = os.environ.get("MY_COWORK_MODEL")
    if provider and model:
        return provider, model
    return model_picker(task_kind)


def _data_dir() -> Path:
    data_dir = Path(
        os.environ.get("MY_COWORK_DATA_DIR")
        or str(Path.home() / ".my-cowork")
    )
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        import tempfile

        data_dir = Path(tempfile.gettempdir()) / "my-cowork"
        data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _seed_mcp_json_from_toml(mcp_json_path: Path, toml_path: Path) -> None:
    """Merge TOML servers into mcp.json if json missing or empty."""
    existing = load_mcp_json(mcp_json_path)
    if existing.get("mcpServers"):
        return
    if not toml_path.is_file():
        return
    servers: dict[str, Any] = {}
    for s in parse_mcp_servers(toml_path):
        entry: dict[str, Any] = {
            "description": s.description,
            "enabled": s.enabled,
        }
        if s.url:
            entry["url"] = s.url
            if s.headers:
                entry["headers"] = s.headers
            if s.transport and s.transport != "http":
                entry["type"] = s.transport
        else:
            entry["command"] = s.command
            entry["args"] = s.args
            entry["env"] = s.env
        servers[s.name] = entry
    if servers:
        save_mcp_json({"mcpServers": servers}, mcp_json_path)


def build_stack(
    supervisor_llm: BaseChatModel | None = None,
    developer_agent_llm: BaseChatModel | None = None,
    document_agent_llm: BaseChatModel | None = None,
    browser_agent_llm: BaseChatModel | None = None,
    multi_modal_agent_llm: BaseChatModel | None = None,
    whitelist: list[str] | None = None,
    mcp_config_path: str | Path | None = None,
    app_tools: list[LoadedAppTool] | None = None,
    admission: Admission | None = None,
    # legacy kwargs
    file_worker_llm: BaseChatModel | None = None,
    doc_worker_llm: BaseChatModel | None = None,
    web_worker_llm: BaseChatModel | None = None,
    msg_worker_llm: BaseChatModel | None = None,
) -> dict[str, Any]:
    """Wire the full backend stack and return a dict of core services."""
    _startup_stage("modules loaded; assembling stores and tools")
    pptx_gen.ensure_templates()

    data_dir = _data_dir()
    from app.workspace.resolver import get_workspace_resolver
    guard = PathGuard(
        whitelist, config_path=data_dir / "directory-permissions.json",
        workspace_paths=lambda: [b.workspace_root for b in get_workspace_resolver().store.list_bindings()],
        read_only_paths=[str(p) for p in [default_skills_root(), default_example_skills_root(), *legacy_user_skills_roots()]],
    )
    from app.runtime.v2.session import configure_session_store

    configure_session_store(data_dir / "sessions.db")
    automation_store = AutomationStore(
        Path(os.environ.get("MY_COWORK_AUTOMATIONS_DB", str(data_dir / "automations.db")))
    )
    audit_store = AuditStore(data_dir / "audit.db")
    command_filter = CommandFilter(audit=audit_store)
    bus = TraceBus()
    trace_store = TraceStore(data_dir / "trace.db")
    bus.subscribe(trace_store.append)
    bus.subscribe(audit_store.on_trace)
    desktop_sessions = DesktopSessionStore(data_dir / "desktop-sessions.db")
    confirm_hub = ConfirmHub(emit=bus.emit, audit=audit_store)
    human_input_hub = HumanInputHub(emit=bus.emit, db_path=data_dir / "human-questions.db")
    from app.memory.embed import make_embed_config

    embed_cfg = make_embed_config()
    if embed_cfg.enabled and embed_cfg.fn is not None:
        long_term = LongTermStore(data_dir / "memory.db", embed_fn=embed_cfg.fn, dim=embed_cfg.dim)
    else:
        long_term = LongTermStore(data_dir / "memory.db")
    memory_settings = MemorySettings(data_dir / "memory-settings.json")
    long_term.memory_settings = memory_settings
    from app.task_support.todo_context import get_todo_runtime

    memory_tools = make_memory_tools(long_term, memory_settings, get_todo_runtime)
    context_tools = make_context_tools()

    set_guard(guard)
    write_tool = make_fs_write(guard, confirm_hub)
    docx_tool = make_docx_tool(guard, confirm_hub)
    gongwen_tool = make_gongwen_format_tool(guard, confirm_hub)
    pptx_tool = make_pptx_tool(guard, confirm_hub)
    xlsx_tool = make_xlsx_tool(guard, confirm_hub)
    pdf_tool = make_pdf_tool(guard, confirm_hub)
    bash_tool = exec_tool.make_bash(
        guard, command_filter, confirm_hub, agent_name="developer_agent"
    )
    document_bash_tool = exec_tool.make_bash(
        guard, command_filter, confirm_hub, agent_name="document_agent"
    )
    single_bash_tool = exec_tool.make_bash(
        guard, command_filter, confirm_hub, agent_name="single_agent"
    )
    lark_tool = make_lark_send_tool(confirm_hub)
    note_tools = make_note_tools()
    ask_human_tool = make_ask_human_tool(human_input_hub)
    automation_tools = make_automation_tools(automation_store, confirm_hub)
    web_search_tool = make_web_search_tool()
    web_fetch_tool = make_web_fetch_tool()
    browser_tools = make_browser_tools(guard, confirm_hub)
    ima_tools = make_ima_tools()

    registry = ToolRegistry()
    industry_tools = [make_agent_tool(item, confirm_hub, admission) for item in (app_tools or [])]
    bus.tool_metadata = {tool.name: dict(tool.metadata or {}) for tool in industry_tools}
    registry.register("builtin.fs.read", fs_read)
    registry.register("builtin.fs.write", write_tool)
    registry.register("builtin.fs.list", fs_list)
    registry.register("builtin.docx.gen", docx_tool)
    registry.register("builtin.pptx.gen", pptx_tool)
    registry.register("builtin.xlsx.gen", xlsx_tool)
    registry.register("builtin.pdf.gen", pdf_tool)
    registry.register("builtin.exec.bash", bash_tool)
    registry.register("builtin.lark.send_message", lark_tool)
    for tool in ima_tools:
        registry.register(f"builtin.ima.{tool.name}", tool)
    for tool in memory_tools:
        registry.register(f"builtin.memory.{tool.name}", tool)
    for tool in context_tools:
        registry.register(f"builtin.context.{tool.name}", tool)
    for tool in industry_tools:
        registry.register(tool.name, tool)

    mcp_json_path = Path(
        os.environ.get("MY_COWORK_MCP_JSON") or str(default_mcp_json_path())
    )
    toml_path = (
        Path(mcp_config_path)
        if mcp_config_path
        else Path(__file__).resolve().parents[2] / "config.toml"
    )
    _seed_mcp_json_from_toml(mcp_json_path, toml_path)

    mcp_manager = McpManager()

    def reload_mcp() -> dict[str, Any]:
        for name in list(mcp_manager.server_names):
            mcp_manager.disconnect(name, registry)
        registry.unregister_prefix("mcp.")
        connected: dict[str, list[str]] = {}
        for cfg in mcp_json_to_configs(load_mcp_json(mcp_json_path)):
            if not cfg.enabled:
                continue
            try:
                connected[cfg.name] = mcp_manager.connect(cfg, registry)
            except Exception as exc:  # noqa: BLE001
                print(f"MCP server {cfg.name!r} failed to start: {exc}", file=sys.stderr)
                connected[cfg.name] = []
        return {"connected": connected}

    _startup_stage("stores and tools ready; connecting MCP")
    reload_mcp()
    _startup_stage("MCP ready; assembling models and graphs")

    def _llm_for(kind: str, override: BaseChatModel | None, fallback: BaseChatModel | None) -> BaseChatModel:
        if override is not None:
            return override
        provider, model = _resolve_llm(kind)
        try:
            return _default_model_factory(provider, model, emit=bus.emit)
        except RuntimeError:
            if fallback is not None:
                return fallback
            raise

    planner_llm = _llm_for("supervisor", supervisor_llm, None)
    developer_llm = _llm_for(
        "developer_agent",
        developer_agent_llm or file_worker_llm,
        planner_llm,
    )
    document_llm = _llm_for(
        "document_agent",
        document_agent_llm or doc_worker_llm,
        developer_llm,
    )
    browser_llm = _llm_for(
        "browser_agent",
        browser_agent_llm or web_worker_llm,
        developer_llm,
    )
    multi_modal_llm = _llm_for(
        "multi_modal_agent",
        multi_modal_agent_llm or msg_worker_llm,
        developer_llm,
    )

    mcp_tools = registry.list_by_prefix("mcp.")
    todo_tool = make_todo_write_tool()
    substep_tool = make_substep_update_tool()
    skills_root = Path(
        os.environ.get("MY_COWORK_SKILLS_ROOT") or str(default_skills_root())
    )
    skills_cfg = Path(
        os.environ.get("MY_COWORK_SKILLS_CONFIG") or str(default_skills_config_path())
    )

    def _skills_for(agent_id: str) -> list:
        return make_skill_tools(
            agent_id, root=skills_root, config_path=skills_cfg
        )

    # Eigent: ObservableTodoToolkit is single-agent only. Workforce Progress
    # is the confirmed sub_tasks list (status via graph todo_state / task_state).
    from app.runtime.v2.office import officecli_available

    office_gen_tools = (
        []
        if officecli_available()
        else [docx_tool, pptx_tool, xlsx_tool]
    )

    checkpointer = get_checkpointer(data_dir / "checkpoints.db")

    # Eigent Single Agent: one meta-agent with the full tool set (no routing).
    from app.industry_apps.file_tools import make_app_file_tools
    single_agent_tools = [
        *make_app_file_tools(),
        todo_tool,
        ask_human_tool,
        *automation_tools,
        *memory_tools,
        *context_tools,
        *_skills_for("single_agent"),
        *note_tools,
        fs_read,
        write_tool,
        fs_list,
        single_bash_tool,
        *office_gen_tools,
        gongwen_tool,
        pdf_tool,
        lark_tool,
        web_search_tool,
        web_fetch_tool,
        *ima_tools,
        *browser_tools,
        *mcp_tools,
        *industry_tools,
    ]

    worker_specs = {
            "developer_agent": {
                "model": developer_llm,
                "tools": [
                    substep_tool,
                    ask_human_tool,
                    *automation_tools,
                    *memory_tools,
                    *context_tools,
                    *_skills_for("developer_agent"),
                    *note_tools,
                    fs_read,
                    write_tool,
                    fs_list,
                    bash_tool,
                    *industry_tools,
                ],
                "prompt_name": "developer",
            },
            "document_agent": {
                "model": document_llm,
                "tools": [
                    substep_tool,
                    ask_human_tool,
                    *automation_tools,
                    *memory_tools,
                    *context_tools,
                    *_skills_for("document_agent"),
                    *note_tools,
                    fs_read,
                    write_tool,
                    fs_list,
                    document_bash_tool,
                    *office_gen_tools,
                    gongwen_tool,
                    pdf_tool,
                    lark_tool,
                    *ima_tools,
                    *industry_tools,
                ],
                "prompt_name": "document",
            },
            "browser_agent": {
                "model": browser_llm,
                "tools": [
                    substep_tool,
                    ask_human_tool,
                    *automation_tools,
                    *memory_tools,
                    *context_tools,
                    *_skills_for("browser_agent"),
                    *note_tools,
                    fs_read,
                    fs_list,
                    web_search_tool,
                    web_fetch_tool,
                    *ima_tools,
                    *browser_tools,
                    *mcp_tools,
                    *industry_tools,
                ],
                "prompt_name": "browser",
            },
            "multi_modal_agent": {
                "model": multi_modal_llm,
                "tools": [
                    substep_tool,
                    ask_human_tool,
                    *automation_tools,
                    *memory_tools,
                    *context_tools,
                    *_skills_for("multi_modal_agent"),
                    *note_tools,
                    fs_read,
                    fs_list,
                    *industry_tools,
                ],
                "prompt_name": "multi_modal",
            },
        }
    graph = compile_workforce_graph(
        workers=worker_specs, planner_llm=planner_llm, checkpointer=checkpointer,
    )
    single_agent_graph = compile_single_agent_graph(
        model=planner_llm,
        tools=single_agent_tools,
        synthesize_llm=planner_llm,
        checkpointer=checkpointer,
    )

    from app.llm.model_config import ModelRegistry
    from app.orchestrator.task_manager import TaskRuntime

    model_registry = ModelRegistry()

    def runtime_factory(config, mode):
        model = gateway.create_configured_model(config)
        # Preserve explicitly configured fallback policy. Capture clients now so
        # later model/credential edits cannot mutate this task's fallback chain.
        from dataclasses import replace
        fallback_models = [model]
        fallback_configs = [config]
        for provider, model_id in _parse_fallback_specs():
            if (provider, model_id) == (config.provider, config.model):
                continue
            fallback_config = model_registry.find_model(provider, model_id)
            if fallback_config is None:
                fallback_config = replace(config, provider=provider, model=model_id,
                    base_url=config.base_url if provider == "openai_compat" else None,
                    reasoning_mode="default", reasoning_effort=None,
                    thinking_enabled=None, thinking_budget=None)
            fallback_models.append(gateway.create_configured_model(fallback_config))
            fallback_configs.append(fallback_config)
        if len(fallback_models) > 1:
            model = FallbackChatModel(fallback_models, model_configs=fallback_configs, on_fallback=lambda index, error: bus.emit({
                "type": "llm.fallback", "from_index": index, "error": type(error).__name__,
            }))
        if mode == "single-agent":
            run_graph = compile_single_agent_graph(
                model=model, tools=single_agent_tools, synthesize_llm=model, checkpointer=checkpointer,
            )
        else:
            run_graph = compile_workforce_graph(
                workers={name: {**spec, "model": model} for name, spec in worker_specs.items()},
                planner_llm=model, checkpointer=checkpointer,
            )
        return TaskRuntime(run_graph, model, config)

    short_term = ShortTermStore(data_dir / "memory.db")
    task_store = TaskStore(data_dir / "tasks.db")
    metrics = MetricsStore(data_dir / "metrics.db")
    task_manager = TaskManager(
        graph=graph,
        tools=registry.list_tools(),
        bus=bus,
        long_term=long_term,
        metrics=metrics,
        max_total_tokens=int(os.environ.get("MY_COWORK_MAX_TOKENS", "200000")),
        planner_llm=planner_llm,
        single_agent_graph=single_agent_graph,
        confirm_hub=confirm_hub,
        human_input_hub=human_input_hub,
        notes_root=data_dir / "notes",
        task_store=task_store,
        short_term=short_term,
        model_registry=model_registry,
        runtime_factory=runtime_factory,
        admission=admission,
    )
    _startup_stage("runtime assembled")
    return {
        "task_manager": task_manager,
        "automation_store": automation_store,
        "bus": bus,
        "confirm_hub": confirm_hub,
        "human_input_hub": human_input_hub,
        "long_term": long_term,
        "memory_settings": memory_settings,
        "short_term": short_term,
        "task_store": task_store,
        "trace_store": trace_store,
        "desktop_sessions": desktop_sessions,
        "audit_store": audit_store,
        "mcp_manager": mcp_manager,
        "mcp_json_path": mcp_json_path,
        "reload_mcp": reload_mcp,
        "registry": registry,
        "data_dir": data_dir,
        "path_guard": guard,
        "graph": graph,
        "single_agent_graph": single_agent_graph,
    }


def _create_app(
    task_manager: Any | None = None,
    bus: Any | None = None,
    confirm_hub: ConfirmHub | None = None,
) -> FastAPI:
    """Create and return the FastAPI application.

    For normal operation call ``create_app()``; dependencies are assembled
    automatically from environment variables. For tests, pass injected
    ``task_manager``, ``bus`` and/or ``confirm_hub``.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        _startup_stage("migrating skills")
        app.state.skills_migration_warnings = []
        if started_stack:
            from app.skills.config import migrate_user_skills
            try:
                app.state.skills_migration_warnings = migrate_user_skills()
            except (OSError, ValueError) as exc:
                app.state.skills_migration_warnings = [f"技能迁移未完成，旧文件已保留：{exc}"]
        automation_scheduler = getattr(app.state, "automation_scheduler", None)
        _startup_stage("skills ready; preparing scheduled tasks")
        if automation_scheduler is not None:
            try:
                import_legacy_jobs(app.state.automations, app.state.legacy_scheduler_db)
            except Exception as exc:  # noqa: BLE001
                print(f"legacy schedule migration failed: {exc}", file=sys.stderr)
            try:
                import_skill_schedules(
                    app.state.automations, root=app.state.skills_root,
                    config_path=app.state.skills_config_path,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"skill schedule import failed: {exc}", file=sys.stderr)
            if not app.state.admission.paused:
                automation_scheduler.start()
        mgr = getattr(app.state, "channels", None)
        _startup_stage("scheduled tasks ready; preparing channels")
        if mgr is not None:
            mgr.bind_loop(asyncio.get_running_loop())
            autostart = os.environ.get("MY_COWORK_CHANNEL_AUTOSTART", "1") != "0"
            if autostart and not app.state.admission.paused and not os.environ.get("PYTEST_CURRENT_TEST"):
                app.state.channels_started = True
                mgr.restore_enabled()
        try:
            _startup_stage("application ready")
            yield
        finally:
            if automation_scheduler is not None:
                await automation_scheduler.stop()
            automation_store = getattr(app.state, "automations", None)
            if automation_store is not None:
                automation_store.close()
            runtime_lock = getattr(app.state, "runtime_lock", None)
            if runtime_lock:
                runtime_lock.close()

    gate = Admission(paused=bool(os.environ.get("MY_COWORK_OPERATION_TOKEN")))
    app = FastAPI(title="my-cowork", lifespan=lifespan)
    app.state.admission = gate
    app.state.generation = __import__("uuid").uuid4().hex
    app.add_middleware(AdmissionMiddleware, admission=gate)
    app.include_router(maintenance_router)

    @app.exception_handler(MaintenanceBusy)
    async def maintenance_busy(request, exc):
        from starlette.responses import JSONResponse
        return JSONResponse({"detail": str(exc)}, status_code=503)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(LocalhostOnlyMiddleware)
    # Injected test/embedded managers need no desktop transport unless a token
    # is configured. Real assembled backends always fail closed without one.
    app.add_middleware(IndustryAppAuthMiddleware, protect_all=task_manager is None or bool(os.environ.get("MY_COWORK_INDUSTRY_TOKEN")))
    app.include_router(chat.router)
    app.include_router(audit_routes.router)
    app.include_router(browser_routes.router)
    app.include_router(desktop_sessions_routes.router)
    app.include_router(confirm.router)
    app.include_router(webhook_lark.router)
    app.include_router(channels_routes.router)
    app.include_router(mcp_routes.router)
    app.include_router(ima_routes.router)
    app.include_router(industry_apps_routes.router)
    from app.server.routes import industry_ai
    app.include_router(industry_ai.router)
    app.include_router(industry_ai.host_router)
    app.include_router(skills_routes.router)
    app.include_router(assistants_routes.router)
    app.include_router(officecli_routes.router)
    app.include_router(memory_routes.router)
    app.include_router(schedule_routes.router)
    app.include_router(automation_routes.router)
    app.include_router(workspace_routes.router)
    from app.server.routes import permissions, model_registry, context
    app.include_router(permissions.router)
    app.include_router(model_registry.router)
    app.include_router(context.router)
    app.include_router(trace_routes.router)
    app.include_router(model_routes.router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    loaded_app_tools: list[LoadedAppTool] = []
    app.state.industry_apps = load_enabled_apps(app, tool_sink=loaded_app_tools)

    started_stack = False
    stack: dict[str, Any] = {}
    if task_manager is None:
        stack = build_stack(app_tools=loaded_app_tools, admission=gate)
        task_manager = stack["task_manager"]
        bus = stack["bus"]
        confirm_hub = stack["confirm_hub"]
        started_stack = True

    if isinstance(task_manager, TaskManager):
        task_manager.admission = gate
        task_manager.app_skills = app.state.app_skills
    app.state.task_manager = task_manager
    app.state.path_guard = stack.get("path_guard")
    app.state.automations = stack.get("automation_store")
    app.state.bus = bus
    app.state.confirm_hub = confirm_hub or ConfirmHub()
    app.state.human_input_hub = getattr(app.state.task_manager, "human_input_hub", None)
    app.state.long_term = stack.get("long_term") or getattr(task_manager, "long_term", None)
    app.state.memory_settings = stack.get("memory_settings")
    app.state.trace_store = stack.get("trace_store")
    app.state.desktop_sessions = stack.get("desktop_sessions")
    app.state.audit_store = stack.get("audit_store")
    app.state.mcp_manager = stack.get("mcp_manager")
    app.state.mcp_json_path = stack.get("mcp_json_path")
    app.state.reload_mcp = stack.get("reload_mcp")
    app.state.skills_config_path = Path(
        os.environ.get("MY_COWORK_SKILLS_CONFIG")
        or str(Path.home() / ".my-cowork" / "skills-config.json")
    )
    app.state.skills_root = Path(
        os.environ.get("MY_COWORK_SKILLS_ROOT") or str(default_skills_root())
    )

    db_env = os.environ.get("MY_COWORK_CHANNELS_DB")
    if db_env:
        channels_db: str | Path = db_env
    elif os.environ.get("PYTEST_CURRENT_TEST"):
        channels_db = ":memory:"
    else:
        channels_db = data_root() / "channels.db"
    app.state.channels = ChannelManager(
        ChannelStore(channels_db),
        task_manager=task_manager,
        send=getattr(app.state, "lark_send", None),
    )

    if started_stack and os.environ.get("MY_COWORK_ENABLE_SCHEDULER", "1") != "0":
        app.state.legacy_scheduler_db = Path(
            os.environ.get("MY_COWORK_SCHEDULER_DB", str(Path.home() / ".my-cowork" / "scheduler.db"))
        )
        app.state.automation_scheduler = AutomationScheduler(
            app.state.automations,
            AutomationRunner(app.state.automations, task_manager, bus),
            admission=gate,
        )

    return app


def create_app(task_manager=None, bus=None, confirm_hub=None):
    if task_manager is not None:
        return _create_app(task_manager, bus, confirm_hub)
    root = app_root()
    lock = FileLock(root, "running")
    try:
        token = os.environ.get("MY_COWORK_OPERATION_TOKEN", "")
        if token:
            lock.acquire()
            runtime_entries(root, token)
        else:
            with FileLock(root, "operation"):
                lock.acquire()
                runtime_entries(root)
        application = _create_app()
        application.state.runtime_lock = lock
        return application
    except BaseException:
        lock.close()
        raise


# Uvicorn entrypoint: ``uvicorn app.main:app``. Lazy so ``from app.main import
# create_app`` in tests does not assemble the real LLM stack at import time.
_app: FastAPI | None = None


def __getattr__(name: str) -> Any:
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def main() -> None:
    """CLI entry for PyInstaller / packaged backend: ``my-cowork-backend --port 0``."""
    import argparse

    # Frozen Windows executables may keep the system code page despite Python
    # environment flags. The desktop pipe protocol is always UTF-8.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    if os.environ.get("MY_COWORK_PARENT_PIPE") == "1" and "--industry-maintenance" not in sys.argv:
        import threading
        def watch_parent():
            try:
                while os.read(sys.stdin.fileno(), 1):
                    pass
            finally:
                os._exit(1)
        threading.Thread(target=watch_parent, daemon=True).start()
    if "--industry-maintenance" in sys.argv:
        from app.industry_apps.maintenance import serve
        serve()
        return
    if "--industry-migrate" in sys.argv:
        from app.industry_apps.lifecycle import migrate_worker
        migrate_worker()
        return
    import uvicorn

    parser = argparse.ArgumentParser(prog="my-cowork-backend")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--browser-smoke", action="store_true", help="Launch bundled Chromium headlessly and verify a screenshot")
    args = parser.parse_args()
    if args.browser_smoke:
        if getattr(sys, "frozen", False) and not os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
            binary_dir = Path(sys.executable).resolve().parent
            for candidate in (binary_dir / "playwright-browsers", binary_dir.parent / "playwright-browsers"):
                if candidate.is_dir():
                    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(candidate)
                    break
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            # --no-shell bundles the full Chromium binary, not headless_shell.
            browser = playwright.chromium.launch(channel="chromium", headless=True)
            try:
                page = browser.new_page()
                page.goto("data:text/html,<title>MyCowork browser smoke</title><h1>ready</h1>")
                assert page.title() == "MyCowork browser smoke"
                assert page.screenshot(type="png").startswith(b"\x89PNG")
            finally:
                browser.close()
        print("BROWSER SMOKE OK", flush=True)
        return
    application = create_app()
    uvicorn.run(application, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
