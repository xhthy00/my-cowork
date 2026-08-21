"""Tests for McpManager against the echo fixture server."""

from pathlib import Path

import pytest

from app.tools.mcp.manager import McpManager, McpServerConfig
from app.tools.registry import ToolRegistry

ECHO = Path(__file__).parent / "fixtures" / "mcp_echo_server.py"


@pytest.fixture()
def manager():
    mgr = McpManager()
    yield mgr
    mgr.close()


def test_mcp_manager_registers_and_invokes_echo(manager: McpManager):
    registry = ToolRegistry()
    names = manager.connect(
        McpServerConfig(name="test", command="python3", args=[str(ECHO)]),
        registry,
    )
    assert "mcp.test.echo" in names
    tool = registry.get("mcp.test.echo")
    result = tool.invoke({"text": "hello-mcp"})
    assert "hello-mcp" in result


def test_mcp_manager_two_servers_do_not_cross(manager: McpManager):
    registry = ToolRegistry()
    manager.connect(
        McpServerConfig(name="a", command="python3", args=[str(ECHO)]),
        registry,
    )
    manager.connect(
        McpServerConfig(name="b", command="python3", args=[str(ECHO)]),
        registry,
    )
    assert "mcp.a.echo" in registry.list_names()
    assert "mcp.b.echo" in registry.list_names()
    assert "hello-a" in registry.get("mcp.a.echo").invoke({"text": "hello-a"})
    assert "hello-b" in registry.get("mcp.b.echo").invoke({"text": "hello-b"})


def test_mcp_json_to_configs_parses_url_and_stdio():
    from app.tools.mcp.manager import mcp_json_to_configs

    cfgs = mcp_json_to_configs(
        {
            "mcpServers": {
                "remote": {
                    "url": "https://example.com/mcp",
                    "headers": {"Authorization": "Bearer x"},
                },
                "sse": {"type": "sse", "url": "https://example.com/events/sse"},
                "implied_sse": {"url": "https://example.com/mcp/sse"},
                "stdio": {"command": "npx", "args": ["-y", "foo"]},
                "skip": {"foo": "bar"},
            }
        }
    )
    by = {c.name: c for c in cfgs}
    assert by["remote"].transport == "http"
    assert by["remote"].url == "https://example.com/mcp"
    assert by["remote"].headers["Authorization"] == "Bearer x"
    assert by["sse"].transport == "sse"
    assert by["implied_sse"].transport == "sse"
    assert by["stdio"].transport == "stdio"
    assert by["stdio"].command == "npx"
    assert "skip" not in by


def test_filter_mcp_tools_enabled_list():
    from langchain_core.tools import StructuredTool

    from app.tools.mcp.manager import filter_mcp_tools

    pw = StructuredTool.from_function(
        lambda: "a",
        name="mcp_playwright_nav",
        description="d",
        metadata={"mcp_server": "playwright"},
    )
    other = StructuredTool.from_function(
        lambda: "b",
        name="mcp_other_foo",
        description="d",
        metadata={"mcp_server": "other"},
    )
    bash = StructuredTool.from_function(lambda: "c", name="bash", description="d")
    names = [t.name for t in filter_mcp_tools([pw, other, bash], ["playwright"])]
    assert names == ["mcp_playwright_nav", "bash"]
    all_names = [t.name for t in filter_mcp_tools([pw, bash], None)]
    assert all_names == ["mcp_playwright_nav", "bash"]


def test_wrapper_blocks_when_server_not_enabled(manager: McpManager):
    from app.tools.mcp.manager import reset_enabled_mcp, set_enabled_mcp

    registry = ToolRegistry()
    manager.connect(
        McpServerConfig(name="test", command="python3", args=[str(ECHO)]),
        registry,
    )
    token = set_enabled_mcp(["playwright"])
    try:
        result = registry.get("mcp.test.echo").invoke({"text": "hello"})
        assert "not enabled" in result
    finally:
        reset_enabled_mcp(token)


def test_http_connect_initialize_and_list(manager: McpManager, monkeypatch: pytest.MonkeyPatch):
    import json

    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode() or "{}")
        method = body.get("method")
        req_id = body.get("id")
        if method == "initialize":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"protocolVersion": "2024-11-05"},
                },
                headers={"mcp-session-id": "sid-1"},
            )
        if method == "notifications/initialized":
            assert request.headers.get("mcp-session-id") == "sid-1"
            return httpx.Response(202)
        if method == "tools/list":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": [
                            {
                                "name": "ping",
                                "description": "ping",
                                "inputSchema": {"type": "object", "properties": {}},
                            }
                        ]
                    },
                },
            )
        if method == "tools/call":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": "pong"}]},
                },
            )
        return httpx.Response(400, text="bad")

    real_client = httpx.Client

    monkeypatch.setattr(
        "app.tools.mcp.manager.httpx.Client",
        lambda *a, **k: real_client(transport=httpx.MockTransport(handler), timeout=60.0),
    )
    registry = ToolRegistry()
    names = manager.connect(
        McpServerConfig(
            name="remote", url="https://example.com/mcp", transport="http"
        ),
        registry,
    )
    assert "mcp.remote.ping" in names
    assert "pong" in registry.get("mcp.remote.ping").invoke({})
