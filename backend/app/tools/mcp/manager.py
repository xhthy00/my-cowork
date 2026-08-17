"""MCP stdio client: per-server reader thread + independent rpc ids.

Adapted config shape from eigent ``mcpConfig.ts`` (``mcpServers`` map).
"""

from __future__ import annotations

import json
import queue
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import Field, create_model

from app.tools.registry import ToolRegistry


@dataclass
class McpServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    description: str = ""
    enabled: bool = True


def parse_mcp_servers(config_path: str | Path) -> list[McpServerConfig]:
    """Parse ``[mcp.servers.<name>]`` sections from a TOML config file."""
    import tomllib

    path = Path(config_path)
    if not path.is_file():
        return []
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    servers = (data.get("mcp") or {}).get("servers") or {}
    result: list[McpServerConfig] = []
    for name, cfg in servers.items():
        result.append(
            McpServerConfig(
                name=str(name),
                command=str(cfg["command"]),
                args=[str(a) for a in cfg.get("args", [])],
                env={str(k): str(v) for k, v in (cfg.get("env") or {}).items()},
                description=str(cfg.get("description") or ""),
                enabled=bool(cfg.get("enabled", True)),
            )
        )
    return result


def default_mcp_json_path() -> Path:
    return Path.home() / ".my-cowork" / "mcp.json"


def load_mcp_json(path: str | Path | None = None) -> dict[str, Any]:
    """Load Eigent-shaped ``{ mcpServers: { name: {command,args,env?} } }``."""
    p = Path(path) if path else default_mcp_json_path()
    if not p.is_file():
        return {"mcpServers": {}}
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"mcpServers": {}}
    servers = data.get("mcpServers") or {}
    return {"mcpServers": dict(servers)}


def save_mcp_json(data: dict[str, Any], path: str | Path | None = None) -> Path:
    p = Path(path) if path else default_mcp_json_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def mcp_json_to_configs(data: dict[str, Any]) -> list[McpServerConfig]:
    servers = data.get("mcpServers") or {}
    out: list[McpServerConfig] = []
    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            continue
        if "url" in cfg and "command" not in cfg:
            # Hosted URL connectors are out of scope for local MCP.
            continue
        args = cfg.get("args") or []
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = [a.strip() for a in args.split(",") if a.strip()]
        out.append(
            McpServerConfig(
                name=str(name),
                command=str(cfg.get("command") or ""),
                args=[str(a) for a in args],
                env={str(k): str(v) for k, v in (cfg.get("env") or {}).items()},
                description=str(cfg.get("description") or ""),
                enabled=bool(cfg.get("enabled", True)),
            )
        )
    return out


class _ServerSession:
    """One MCP stdio process with a dedicated reader thread and rpc id space."""

    def __init__(self, name: str, proc: subprocess.Popen[str]) -> None:
        self.name = name
        self.proc = proc
        self._lock = threading.Lock()
        self._next_id = 1
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._alive = True
        self._thread = threading.Thread(target=self._reader, name=f"mcp-{name}", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._alive = False
        try:
            self.proc.terminate()
            self.proc.wait(timeout=2)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass

    def _reader(self) -> None:
        assert self.proc.stdout is not None
        while self._alive:
            line = self.proc.stdout.readline()
            if not line:
                break
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            req_id = data.get("id")
            if req_id is None:
                continue
            with self._lock:
                q = self._pending.get(int(req_id))
            if q is not None:
                q.put(data)

    def notify(self, method: str, params: dict[str, Any]) -> None:
        assert self.proc.stdin is not None
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        with self._lock:
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()

    def rpc(self, method: str, params: dict[str, Any], timeout: float = 60.0) -> dict[str, Any]:
        assert self.proc.stdin is not None
        wait: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        with self._lock:
            req_id = self._next_id
            self._next_id += 1
            self._pending[req_id] = wait
            msg = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()
        try:
            data = wait.get(timeout=timeout)
        finally:
            with self._lock:
                self._pending.pop(req_id, None)
        if "error" in data:
            raise RuntimeError(f"MCP error ({self.name}): {data['error']}")
        return data.get("result") or {}


class McpManager:
    """Spawn multiple MCP stdio servers and register their tools."""

    def __init__(self) -> None:
        self._sessions: dict[str, _ServerSession] = {}
        self._tool_names: dict[str, list[str]] = {}

    @property
    def server_names(self) -> list[str]:
        return list(self._sessions.keys())

    def close(self) -> None:
        for session in list(self._sessions.values()):
            session.close()
        self._sessions.clear()
        self._tool_names.clear()

    def disconnect(self, name: str, registry: ToolRegistry | None = None) -> None:
        session = self._sessions.pop(name, None)
        names = self._tool_names.pop(name, [])
        if registry is not None:
            for dotted in names:
                registry.unregister(dotted)
        if session is not None:
            session.close()

    def connect(self, config: McpServerConfig, registry: ToolRegistry) -> list[str]:
        """Start one MCP server and register ``mcp.<name>.<tool>`` wrappers."""
        if not config.enabled:
            return []
        if not config.command:
            raise ValueError(f"MCP server {config.name!r} missing command")
        if config.name in self._sessions:
            self.disconnect(config.name, registry)

        env = None
        if config.env:
            import os

            env = {**os.environ, **config.env}

        proc = subprocess.Popen(
            [config.command, *config.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )
        session = _ServerSession(config.name, proc)
        self._sessions[config.name] = session

        try:
            session.rpc(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "my-cowork", "version": "0.1.0"},
                },
            )
            session.notify("notifications/initialized", {})
            listed = session.rpc("tools/list", {})
        except Exception:
            self.disconnect(config.name, registry)
            raise

        tools = listed.get("tools") or []
        names: list[str] = []
        for tool in tools:
            tool_name = str(tool["name"])
            dotted = f"mcp.{config.name}.{tool_name}"
            wrapper = self._make_wrapper(session, config.name, tool)
            registry.register(dotted, wrapper)
            names.append(dotted)
        self._tool_names[config.name] = names
        return names

    def _make_wrapper(self, session: _ServerSession, server: str, tool: dict[str, Any]):
        tool_name = str(tool["name"])
        description = str(tool.get("description") or tool_name)
        schema = tool.get("inputSchema") or {"type": "object", "properties": {}}

        props = schema.get("properties") or {}
        fields: dict[str, Any] = {}
        for key, prop in props.items():
            fields[key] = (Any, Field(default=None, description=str(prop.get("description", ""))))
        if not fields:
            fields["payload"] = (Any, Field(default=None, description="Raw tool input"))
        ArgsModel = create_model(f"Mcp{server}_{tool_name}_Args", **fields)  # type: ignore[call-overload]

        def _invoke(**kwargs: Any) -> str:
            args = {k: v for k, v in kwargs.items() if v is not None}
            if "payload" in args and not props:
                value = args.pop("payload")
                if isinstance(value, str):
                    try:
                        args = json.loads(value)
                    except json.JSONDecodeError:
                        args = {"text": value}
            result = session.rpc(
                "tools/call",
                {"name": tool_name, "arguments": args},
            )
            content = result.get("content") or []
            texts = [
                str(part.get("text", ""))
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            ]
            return "\n".join(texts) if texts else json.dumps(result)

        return StructuredTool.from_function(
            func=_invoke,
            name=f"mcp_{server}_{tool_name}",
            description=description,
            args_schema=ArgsModel,
        )
