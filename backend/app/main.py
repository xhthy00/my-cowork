"""Application assembly point.

This module is intentionally outside the harness layer contract. It is the
only place allowed to instantiate and wire the 9 layers together.
"""

from __future__ import annotations

import asyncio
import os
import sys

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

from app.agents.factory import (
    create_single_agent,
    create_worker,
    load_single_agent_prompt,
    load_worker_prompt,
)
from app.graphs.single_agent import compile_single_agent_graph
from app.graphs.workforce import compile_workforce_graph
from app.guardrails.approval import ConfirmHub
from app.guardrails.audit import AuditStore
from app.guardrails.command_filter import CommandFilter
from app.llm import gateway, model_picker
from app.llm.fallback import FallbackChatModel
from app.memory.long_term import LongTermStore
from app.memory.short_term import ShortTermStore
from app.observability.metrics import MetricsStore
from app.observability.trace import TraceBus
from app.observability.trace_store import TraceStore
from app.orchestrator.task_manager import TaskManager
from app.orchestrator.task_store import TaskStore
from app.orchestrator.scheduler import SkillScheduler
from app.runtime.checkpointer import get_checkpointer
from app.sandbox.path_guard import PathGuard, desktop_dir
from app.workspace.paths import data_root
from app.server.localhost_only import LocalhostOnlyMiddleware
from app.server.channels.manager import ChannelManager
from app.server.channels.store import ChannelStore
from app.server.routes import (
    assistants as assistants_routes,
    channels as channels_routes,
    chat,
    confirm,
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
from app.tools.builtin.skills import make_skill_tools
from app.tools.builtin.todo import make_todo_write_tool
from app.skills.config import default_skills_config_path, default_skills_root
from app.tools.mcp.manager import (
    McpManager,
    default_mcp_json_path,
    load_mcp_json,
    mcp_json_to_configs,
    parse_mcp_servers,
    save_mcp_json,
)
from app.tools.registry import ToolRegistry


def _default_whitelist() -> list[str]:
    return [str(Path.home())]


def _path_hints() -> str:
    home = Path.home()
    desk = desktop_dir()
    return (
        f"- User home: `{home}`\n"
        f"- Desktop (only if the user explicitly asks): `{desk}`\n"
        f"- Default: write deliverables under the task working directory "
        f"injected in each run (see [工作空间约束])."
    )


_SKILLS_WORKFLOW = """
<skills_system>
Skills are your primary specialized workflows (Eigent SkillToolkit).
- Trigger: If the user references a skill with double curly braces (e.g. {{pptx}})
  or the task clearly matches a skill domain, you MUST use the skill workflow first.
- Steps:
  1. Call `list_skills` to confirm exact available skill names.
  2. Call `load_skill` for the best matching skill before domain work.
  3. Follow the loaded skill as the primary plan (process, constraints, output format).
- Do not rely on memory for skill details; always use loaded content.
- If multiple skills apply, prioritize the most specific one and load others as needed.
</skills_system>
""".strip()


def _skills_prompt_for(agent_id: str) -> str:
    """Eigent: workflow block + catalog (tools also expose list/load)."""
    lines = [_SKILLS_WORKFLOW, ""]
    try:
        from app.skills.config import list_skills_api, skill_visible_for_agent

        if agent_id == "single_agent":
            skills = [s for s in list_skills_api() if s.get("enabled", True)]
        else:
            skills = [
                s
                for s in list_skills_api()
                if skill_visible_for_agent(s, agent_id)
            ]
    except Exception:
        skills = []
    if skills:
        lines.append("Available skills (use list_skills / load_skill to fetch full body):")
        for s in skills:
            lines.append(f"- {s['id']}: {s.get('description') or s.get('name')}")
    else:
        lines.append("Available skills: (none configured — list_skills may still find disk skills).")
    return "\n".join(lines)


def _with_skills(base: str, agent_id: str) -> str:
    block = _skills_prompt_for(agent_id)
    return f"{base}\n\n{block}" if block else base


def _developer_prompt() -> str:
    template = load_worker_prompt("developer_agent")
    return _with_skills(
        template.replace("{path_hints}", _path_hints()), "developer_agent"
    )


def _document_prompt() -> str:
    template = load_worker_prompt("document_agent")
    return _with_skills(
        template.replace("{path_hints}", _path_hints()), "document_agent"
    )


def _single_agent_prompt() -> str:
    template = load_single_agent_prompt()
    return _with_skills(
        template.replace("{path_hints}", _path_hints()),
        "single_agent",
    )


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
        servers[s.name] = {
            "command": s.command,
            "args": s.args,
            "env": s.env,
            "description": s.description,
            "enabled": s.enabled,
        }
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
    # legacy kwargs
    file_worker_llm: BaseChatModel | None = None,
    doc_worker_llm: BaseChatModel | None = None,
    web_worker_llm: BaseChatModel | None = None,
    msg_worker_llm: BaseChatModel | None = None,
) -> dict[str, Any]:
    """Wire the full backend stack and return a dict of core services."""
    pptx_gen.ensure_templates()

    guard = PathGuard(whitelist or _default_whitelist())
    data_dir = _data_dir()
    audit_store = AuditStore(data_dir / "audit.db")
    command_filter = CommandFilter(audit=audit_store)
    bus = TraceBus()
    trace_store = TraceStore(data_dir / "trace.db")
    bus.subscribe(trace_store.append)
    confirm_hub = ConfirmHub(emit=bus.emit, audit=audit_store)

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
    lark_tool = make_lark_send_tool()
    note_tools = make_note_tools()

    registry = ToolRegistry()
    registry.register("builtin.fs.read", fs_read)
    registry.register("builtin.fs.write", write_tool)
    registry.register("builtin.fs.list", fs_list)
    registry.register("builtin.docx.gen", docx_tool)
    registry.register("builtin.pptx.gen", pptx_tool)
    registry.register("builtin.xlsx.gen", xlsx_tool)
    registry.register("builtin.pdf.gen", pdf_tool)
    registry.register("builtin.exec.bash", bash_tool)
    registry.register("builtin.lark.send_message", lark_tool)

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

    reload_mcp()

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
    developer_agent = create_worker(
        "developer_agent",
        system_prompt=_developer_prompt(),
        model=developer_llm,
        tools=[
            *_skills_for("developer_agent"),
            *note_tools,
            fs_read,
            write_tool,
            fs_list,
            bash_tool,
        ],
    )
    document_agent = create_worker(
        "document_agent",
        system_prompt=_document_prompt(),
        model=document_llm,
        tools=[
            *_skills_for("document_agent"),
            *note_tools,
            fs_read,
            write_tool,
            fs_list,
            document_bash_tool,
            docx_tool,
            gongwen_tool,
            pptx_tool,
            xlsx_tool,
            pdf_tool,
            lark_tool,
        ],
    )
    browser_agent = create_worker(
        "browser_agent",
        system_prompt=_with_skills(
            load_worker_prompt("browser_agent"), "browser_agent"
        ),
        model=browser_llm,
        tools=[
            *_skills_for("browser_agent"),
            *note_tools,
            fs_read,
            fs_list,
            *mcp_tools,
        ],
    )
    multi_modal_agent = create_worker(
        "multi_modal_agent",
        system_prompt=_with_skills(
            load_worker_prompt("multi_modal_agent"), "multi_modal_agent"
        ),
        model=multi_modal_llm,
        tools=[
            *_skills_for("multi_modal_agent"),
            *note_tools,
            fs_read,
            fs_list,
        ],
    )

    checkpointer = get_checkpointer(data_dir / "checkpoints.db")
    graph = compile_workforce_graph(
        workers={
            "developer_agent": developer_agent,
            "document_agent": document_agent,
            "browser_agent": browser_agent,
            "multi_modal_agent": multi_modal_agent,
        },
        checkpointer=checkpointer,
    )

    # Eigent Single Agent: one meta-agent with the full tool set (no routing).
    single_agent_tools = [
        todo_tool,
        *_skills_for("single_agent"),
        *note_tools,
        fs_read,
        write_tool,
        fs_list,
        single_bash_tool,
        docx_tool,
        gongwen_tool,
        pptx_tool,
        xlsx_tool,
        pdf_tool,
        lark_tool,
        *mcp_tools,
    ]
    single_agent = create_single_agent(
        system_prompt=_single_agent_prompt(),
        model=planner_llm,
        tools=single_agent_tools,
    )
    single_agent_graph = compile_single_agent_graph(
        single_agent, checkpointer=checkpointer
    )

    long_term = LongTermStore(data_dir / "memory.db")
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
        notes_root=data_dir / "notes",
        task_store=task_store,
        short_term=short_term,
    )
    return {
        "task_manager": task_manager,
        "bus": bus,
        "confirm_hub": confirm_hub,
        "long_term": long_term,
        "short_term": short_term,
        "task_store": task_store,
        "trace_store": trace_store,
        "audit_store": audit_store,
        "mcp_manager": mcp_manager,
        "mcp_json_path": mcp_json_path,
        "reload_mcp": reload_mcp,
        "registry": registry,
        "data_dir": data_dir,
        "graph": graph,
        "single_agent_graph": single_agent_graph,
    }


def create_app(
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
        mgr = getattr(app.state, "channels", None)
        if mgr is not None:
            mgr.bind_loop(asyncio.get_running_loop())
            autostart = os.environ.get("MY_COWORK_CHANNEL_AUTOSTART", "1") != "0"
            if autostart and not os.environ.get("PYTEST_CURRENT_TEST"):
                mgr.restore_enabled()
        yield

    app = FastAPI(title="my-cowork", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(LocalhostOnlyMiddleware)
    app.include_router(chat.router)
    app.include_router(confirm.router)
    app.include_router(webhook_lark.router)
    app.include_router(channels_routes.router)
    app.include_router(mcp_routes.router)
    app.include_router(skills_routes.router)
    app.include_router(assistants_routes.router)
    app.include_router(officecli_routes.router)
    app.include_router(memory_routes.router)
    app.include_router(schedule_routes.router)
    app.include_router(workspace_routes.router)
    app.include_router(trace_routes.router)
    app.include_router(model_routes.router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    started_stack = False
    stack: dict[str, Any] = {}
    if task_manager is None:
        stack = build_stack()
        task_manager = stack["task_manager"]
        bus = stack["bus"]
        confirm_hub = stack["confirm_hub"]
        started_stack = True

    app.state.task_manager = task_manager
    app.state.bus = bus
    app.state.confirm_hub = confirm_hub or ConfirmHub()
    app.state.long_term = stack.get("long_term") or getattr(task_manager, "long_term", None)
    app.state.trace_store = stack.get("trace_store")
    app.state.audit_store = stack.get("audit_store")
    app.state.mcp_manager = stack.get("mcp_manager")
    app.state.mcp_json_path = stack.get("mcp_json_path")
    app.state.reload_mcp = stack.get("reload_mcp")
    app.state.skills_config_path = Path(
        os.environ.get("MY_COWORK_SKILLS_CONFIG")
        or str(Path.home() / ".my-cowork" / "skills-config.json")
    )
    app.state.skills_root = Path(
        os.environ.get("MY_COWORK_SKILLS_ROOT")
        or str(Path(__file__).resolve().parents[2] / "skills")
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
        db = Path(os.environ.get("MY_COWORK_SCHEDULER_DB", str(Path.home() / ".my-cowork" / "scheduler.db")))
        db.parent.mkdir(parents=True, exist_ok=True)
        try:
            sched = SkillScheduler(task_manager=task_manager, db_path=db)
            sched.start()
            sched.register_discovered()
            app.state.scheduler = sched
        except Exception as exc:  # noqa: BLE001
            print(f"scheduler failed to start: {exc}", file=sys.stderr)

    return app


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

    import uvicorn

    parser = argparse.ArgumentParser(prog="my-cowork-backend")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    application = create_app()
    uvicorn.run(application, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
