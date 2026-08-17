"""MCP Connectors HTTP API — local MCP only (Eigent brain mcp CRUD shape)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.tools.mcp.manager import (
    McpServerConfig,
    load_mcp_json,
    mcp_json_to_configs,
    save_mcp_json,
)

router = APIRouter()


class McpServersBody(BaseModel):
    mcpServers: dict[str, Any] = Field(default_factory=dict)


@router.get("/api/mcp/servers")
async def get_servers(request: Request) -> dict[str, Any]:
    path = getattr(request.app.state, "mcp_json_path", None)
    data = load_mcp_json(path)
    mgr = getattr(request.app.state, "mcp_manager", None)
    live = set(mgr.server_names) if mgr is not None else set()
    enriched = {}
    for name, cfg in (data.get("mcpServers") or {}).items():
        item = dict(cfg) if isinstance(cfg, dict) else {"raw": cfg}
        item["connected"] = name in live
        enriched[name] = item
    return {"mcpServers": enriched}


@router.put("/api/mcp/servers")
async def put_servers(body: McpServersBody, request: Request) -> dict[str, Any]:
    path = getattr(request.app.state, "mcp_json_path", None)
    save_mcp_json({"mcpServers": body.mcpServers}, path)
    return {"ok": True, "mcpServers": body.mcpServers}


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
