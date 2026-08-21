"""MCP client: stdio + Streamable HTTP + SSE.

Adapted config shape from eigent ``mcpConfig.ts`` (``mcpServers`` map).
"""

from __future__ import annotations

import json
import queue
import re
import subprocess
import threading
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urljoin

import httpx
from langchain_core.tools import StructuredTool
from pydantic import Field, create_model

from app.tools.registry import ToolRegistry

_enabled_mcp: ContextVar[list[str] | None] = ContextVar("enabled_mcp", default=None)


def set_enabled_mcp(names: list[str] | None) -> Token:
    """Bind the MCP servers allowed for this task. ``None`` means all."""
    return _enabled_mcp.set(list(names) if names is not None else None)


def get_enabled_mcp() -> list[str] | None:
    return _enabled_mcp.get()


def reset_enabled_mcp(token: Token) -> None:
    _enabled_mcp.reset(token)


def mcp_name_token(name: str) -> str:
    """Composer ``@`` slug: spaces → ``_``, drop non-ASCII/punctuation, casefold."""
    slug = re.sub(r"\s+", "_", str(name).strip())
    slug = re.sub(r"[^A-Za-z0-9_-]", "", slug)
    return slug.casefold()


@dataclass
class McpServerConfig:
    name: str
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    description: str = ""
    enabled: bool = True
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    transport: str = "stdio"


def infer_mcp_transport(cfg: dict[str, Any]) -> str:
    """Map eigent/Cursor json fields to ``stdio`` | ``http`` | ``sse``."""
    raw = str(cfg.get("transport") or cfg.get("type") or "").lower().strip()
    if raw in {"stdio"}:
        return "stdio"
    if raw in {"sse"}:
        return "sse"
    if raw in {"http", "streamable_http", "streamable-http"}:
        return "http"
    url = str(cfg.get("url") or "")
    if url:
        if "/sse" in url.lower():
            return "sse"
        return "http"
    return "stdio"


def _str_map(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}


def _parse_args(raw: Any) -> list[str]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return [a.strip() for a in raw.split(",") if a.strip()]
    if isinstance(raw, list):
        return [str(a) for a in raw]
    return []


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
        if not isinstance(cfg, dict):
            continue
        transport = infer_mcp_transport(cfg)
        result.append(
            McpServerConfig(
                name=str(name),
                command=str(cfg.get("command") or ""),
                args=_parse_args(cfg.get("args")),
                env=_str_map(cfg.get("env")),
                description=str(cfg.get("description") or ""),
                enabled=bool(cfg.get("enabled", True)),
                url=str(cfg.get("url") or ""),
                headers=_str_map(cfg.get("headers")),
                transport=transport,
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
        transport = infer_mcp_transport(cfg)
        command = str(cfg.get("command") or "")
        url = str(cfg.get("url") or "")
        if transport == "stdio" and not command:
            continue
        if transport in {"http", "sse"} and not url:
            continue
        out.append(
            McpServerConfig(
                name=str(name),
                command=command,
                args=_parse_args(cfg.get("args")),
                env=_str_map(cfg.get("env")),
                description=str(cfg.get("description") or ""),
                enabled=bool(cfg.get("enabled", True)),
                url=url,
                headers=_str_map(cfg.get("headers")),
                transport=transport,
            )
        )
    return out


def _mcp_server_of(tool: Any) -> str | None:
    meta = getattr(tool, "metadata", None) or {}
    if isinstance(meta, dict) and meta.get("mcp_server"):
        return str(meta["mcp_server"])
    name = str(getattr(tool, "name", "") or "")
    if name.startswith("mcp."):
        parts = name.split(".")
        if len(parts) >= 2 and parts[1]:
            return parts[1]
    if name.startswith("mcp_"):
        rest = name[4:]
        return rest.split("_", 1)[0] if rest else None
    return None


def filter_mcp_tools(tools: list[Any] | None, enabled_mcp: list[str] | None) -> list[Any]:
    """Keep non-MCP tools always; when *enabled_mcp* is a list, keep only those servers.

    ``None`` / omitted = all MCP tools (chat without ``@连接器``).
    """
    items = list(tools or [])
    if enabled_mcp is None:
        return items
    allowed = {mcp_name_token(s) for s in enabled_mcp}
    out: list[Any] = []
    for tool in items:
        server = _mcp_server_of(tool)
        if server is None:
            out.append(tool)
        elif mcp_name_token(server) in allowed:
            out.append(tool)
    return out


class _RpcSession(Protocol):
    name: str

    def close(self) -> None: ...

    def notify(self, method: str, params: dict[str, Any]) -> None: ...

    def rpc(self, method: str, params: dict[str, Any], timeout: float = 60.0) -> dict[str, Any]: ...


def _rpc_result(name: str, data: dict[str, Any]) -> dict[str, Any]:
    if "error" in data:
        raise RuntimeError(f"MCP error ({name}): {data['error']}")
    return data.get("result") or {}


def _iter_sse_json(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if not data_lines:
            continue
        try:
            obj = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _jsonrpc_from_http_response(resp: httpx.Response, req_id: Any) -> dict[str, Any]:
    if not resp.content:
        return {}
    ctype = (resp.headers.get("content-type") or "").lower()
    if "text/event-stream" in ctype:
        payloads = _iter_sse_json(resp.text)
        for obj in payloads:
            if req_id is None or obj.get("id") == req_id:
                return obj
        return payloads[-1] if payloads else {}
    try:
        data = resp.json()
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


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
        return _rpc_result(self.name, data)


class _HttpSession:
    """Streamable HTTP: POST JSON-RPC, honor ``Mcp-Session-Id``."""

    def __init__(
        self,
        name: str,
        url: str,
        headers: dict[str, str] | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.name = name
        self.url = url
        self._headers = dict(headers or {})
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=60.0)
        self._session_id: str | None = None
        self._lock = threading.Lock()
        self._next_id = 1

    def close(self) -> None:
        if self._owns_client:
            try:
                self._client.close()
            except Exception:
                pass

    def _request_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **self._headers,
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    def _capture_session(self, resp: httpx.Response) -> None:
        sid = resp.headers.get("mcp-session-id") or resp.headers.get("Mcp-Session-Id")
        if sid:
            self._session_id = sid

    def notify(self, method: str, params: dict[str, Any]) -> None:
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        resp = self._client.post(self.url, json=msg, headers=self._request_headers())
        self._capture_session(resp)
        resp.raise_for_status()

    def rpc(self, method: str, params: dict[str, Any], timeout: float = 60.0) -> dict[str, Any]:
        with self._lock:
            req_id = self._next_id
            self._next_id += 1
        msg = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        resp = self._client.post(
            self.url, json=msg, headers=self._request_headers(), timeout=timeout
        )
        self._capture_session(resp)
        resp.raise_for_status()
        return _rpc_result(self.name, _jsonrpc_from_http_response(resp, req_id))


class _SseSession:
    """Legacy MCP SSE: GET event stream, POST JSON-RPC to the advertised endpoint."""

    def __init__(
        self,
        name: str,
        url: str,
        headers: dict[str, str] | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.name = name
        self._url = url
        self._headers = dict(headers or {})
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=60.0)
        self._post = client or httpx.Client(timeout=60.0)
        self._lock = threading.Lock()
        self._next_id = 1
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._alive = True
        self._endpoint: str | None = None
        self._endpoint_ready = threading.Event()
        self._error: str | None = None
        self._thread = threading.Thread(target=self._reader, name=f"mcp-sse-{name}", daemon=True)
        self._thread.start()
        if not self._endpoint_ready.wait(timeout=30):
            self.close()
            raise RuntimeError(self._error or f"MCP SSE endpoint timeout ({name})")

    def close(self) -> None:
        self._alive = False
        self._endpoint_ready.set()
        if self._owns_client:
            for cli in {self._client, self._post}:
                try:
                    cli.close()
                except Exception:
                    pass

    def _dispatch(self, event_type: str, data: str) -> None:
        if event_type == "endpoint":
            loc = data.strip()
            self._endpoint = loc if loc.startswith("http") else urljoin(self._url, loc)
            self._endpoint_ready.set()
            return
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            return
        if not isinstance(obj, dict):
            return
        req_id = obj.get("id")
        if req_id is None:
            return
        with self._lock:
            q = self._pending.get(int(req_id))
        if q is not None:
            q.put(obj)

    def _reader(self) -> None:
        headers = {**self._headers, "Accept": "text/event-stream"}
        try:
            with self._client.stream("GET", self._url, headers=headers, timeout=None) as resp:
                resp.raise_for_status()
                event_type = "message"
                data_lines: list[str] = []
                for line in resp.iter_lines():
                    if not self._alive:
                        break
                    if line == "":
                        if data_lines:
                            self._dispatch(event_type, "\n".join(data_lines))
                        event_type = "message"
                        data_lines = []
                        continue
                    if line.startswith("event:"):
                        event_type = line[6:].strip() or "message"
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].lstrip())
                if data_lines and self._alive:
                    self._dispatch(event_type, "\n".join(data_lines))
        except Exception as exc:  # noqa: BLE001
            self._error = str(exc)
            self._endpoint_ready.set()

    def notify(self, method: str, params: dict[str, Any]) -> None:
        if not self._endpoint:
            raise RuntimeError(f"MCP SSE endpoint missing ({self.name})")
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        resp = self._post.post(
            self._endpoint,
            json=msg,
            headers={**self._headers, "Content-Type": "application/json"},
        )
        resp.raise_for_status()

    def rpc(self, method: str, params: dict[str, Any], timeout: float = 60.0) -> dict[str, Any]:
        if not self._endpoint:
            raise RuntimeError(f"MCP SSE endpoint missing ({self.name})")
        wait: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        with self._lock:
            req_id = self._next_id
            self._next_id += 1
            self._pending[req_id] = wait
        msg = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        try:
            resp = self._post.post(
                self._endpoint,
                json=msg,
                headers={**self._headers, "Content-Type": "application/json"},
                timeout=timeout,
            )
            resp.raise_for_status()
            inline = _jsonrpc_from_http_response(resp, req_id)
            if inline.get("result") is not None or "error" in inline:
                return _rpc_result(self.name, inline)
            data = wait.get(timeout=timeout)
        finally:
            with self._lock:
                self._pending.pop(req_id, None)
        return _rpc_result(self.name, data)


class McpManager:
    """Spawn MCP servers (stdio / HTTP / SSE) and register their tools."""

    def __init__(self) -> None:
        self._sessions: dict[str, _RpcSession] = {}
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

    def _open_session(self, config: McpServerConfig) -> _RpcSession:
        transport = config.transport or "stdio"
        if config.url and transport == "stdio":
            transport = infer_mcp_transport({"url": config.url, "type": config.transport})
        if transport == "sse":
            if not config.url:
                raise ValueError(f"MCP server {config.name!r} missing url")
            return _SseSession(config.name, config.url, config.headers)
        if transport == "http" or config.url:
            if not config.url:
                raise ValueError(f"MCP server {config.name!r} missing url")
            return _HttpSession(config.name, config.url, config.headers)
        if not config.command:
            raise ValueError(f"MCP server {config.name!r} missing command")
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
        return _ServerSession(config.name, proc)

    def connect(self, config: McpServerConfig, registry: ToolRegistry) -> list[str]:
        """Start one MCP server and register ``mcp.<name>.<tool>`` wrappers."""
        if not config.enabled:
            return []
        if config.name in self._sessions:
            self.disconnect(config.name, registry)

        session = self._open_session(config)
        self._sessions[config.name] = session

        try:
            session.rpc(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "my-cowork", "version": "0.1.0"},
                },
                timeout=15.0,
            )
            session.notify("notifications/initialized", {})
            listed = session.rpc("tools/list", {}, timeout=15.0)
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

    def _make_wrapper(self, session: _RpcSession, server: str, tool: dict[str, Any]):
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
            allowed = get_enabled_mcp()
            if allowed is not None and mcp_name_token(server) not in {
                mcp_name_token(s) for s in allowed
            }:
                return (
                    f"[ERROR] MCP server {server!r} is not enabled for this message."
                )
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
            metadata={"mcp_server": server},
        )
