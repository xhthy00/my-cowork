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
