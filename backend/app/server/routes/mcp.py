"""MCP Connectors HTTP API — local + remote MCP (Eigent custom mcp CRUD shape)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field

from app.tools.mcp.manager import (
    load_mcp_json,
    mcp_json_to_configs,
    save_mcp_json,
)

router = APIRouter()


class McpServersBody(BaseModel):
    mcpServers: dict[str, Any] = Field(default_factory=dict)


def _reload_app(app: Any) -> dict[str, Any]:
    """Connect MCP processes off the request path (npx/HTTP can take a while)."""
    reload_fn = getattr(app.state, "reload_mcp", None)
    if reload_fn is None:
        return {}
    try:
        result = reload_fn()
    except Exception as exc:  # noqa: BLE001
        print(f"MCP reload failed: {exc}", flush=True)
        return {}
    return result if isinstance(result, dict) else {}


def _enriched(request: Request, servers: dict[str, Any]) -> dict[str, Any]:
    mgr = getattr(request.app.state, "mcp_manager", None)
    live = set(mgr.server_names) if mgr is not None else set()
    out: dict[str, Any] = {}
    for name, cfg in servers.items():
        item = dict(cfg) if isinstance(cfg, dict) else {"raw": cfg}
        item["connected"] = name in live
        out[name] = item
    return out


@router.get("/api/mcp/servers")
async def get_servers(request: Request) -> dict[str, Any]:
    path = getattr(request.app.state, "mcp_json_path", None)
    data = load_mcp_json(path)
    return {"mcpServers": _enriched(request, data.get("mcpServers") or {})}


@router.put("/api/mcp/servers")
async def put_servers(
    body: McpServersBody, request: Request, background_tasks: BackgroundTasks
) -> dict[str, Any]:
    path = getattr(request.app.state, "mcp_json_path", None)
    save_mcp_json({"mcpServers": body.mcpServers}, path)
    background_tasks.add_task(_reload_app, request.app)
    return {
        "ok": True,
        "mcpServers": body.mcpServers,
        "connected": {},
    }


@router.post("/api/mcp/import")
async def import_servers(
    body: McpServersBody, request: Request, background_tasks: BackgroundTasks
) -> dict[str, Any]:
    incoming = body.mcpServers or {}
    if not incoming:
        raise HTTPException(status_code=400, detail="mcpServers required")
    path = getattr(request.app.state, "mcp_json_path", None)
    current = load_mcp_json(path)
    existing = dict(current.get("mcpServers") or {})
    existing_lower = {str(n).lower(): n for n in existing}
    dups: list[str] = []
    for name in incoming:
        hit = existing_lower.get(str(name).lower())
        if hit is not None:
            dups.append(str(hit))
    if dups:
        raise HTTPException(
            status_code=409, detail=f"已存在：{', '.join(dups)}"
        )
    merged = {**existing, **incoming}
    save_mcp_json({"mcpServers": merged}, path)
    background_tasks.add_task(_reload_app, request.app)
    return {
        "ok": True,
        "mcpServers": merged,
        "connected": {},
    }


@router.post("/api/mcp/servers/{name}/test")
async def test_server(name: str, request: Request) -> dict[str, Any]:
    path = getattr(request.app.state, "mcp_json_path", None)
    data = load_mcp_json(path)
    cfg_map = {c.name: c for c in mcp_json_to_configs(data)}
    if name not in cfg_map:
        raise HTTPException(status_code=404, detail="server not found")
    cfg = cfg_map[name]
    from app.tools.mcp.manager import McpManager
    from app.tools.registry import ToolRegistry

    mgr = McpManager()
    registry = ToolRegistry()
    try:
        names = mgr.connect(cfg, registry)
        return {"ok": True, "tools": names}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        mgr.close()


@router.post("/api/mcp/reload")
async def reload_mcp(request: Request) -> dict[str, Any]:
    reload_fn = getattr(request.app.state, "reload_mcp", None)
    if reload_fn is None:
        raise HTTPException(status_code=501, detail="mcp reload not configured")
    try:
        result = reload_fn()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True, **(result or {})}
