"""API tests for skills / memory / mcp routes."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.main import create_app
from app.memory.long_term import LongTermStore
from app.skills.config import save_skills_config


class FakeTaskManager:
    async def handle(self, req):
        if False:
            yield {}


@pytest.fixture()
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    skill_dir = skills_root / "demo"
    skill_dir.mkdir()
    (skill_dir / "skill.yaml").write_text(
        "id: demo\nname: Demo\ndescription: d\nprompt: hi\n",
        encoding="utf-8",
    )
    cfg = tmp_path / "skills-config.json"
    save_skills_config({"version": 1, "skills": {}}, cfg)
    mcp_json = tmp_path / "mcp.json"
    mcp_json.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    mem = LongTermStore(tmp_path / "memory.db")

    application = create_app(task_manager=FakeTaskManager(), bus=None)
    application.state.skills_root = skills_root
    application.state.skills_config_path = cfg
    application.state.mcp_json_path = mcp_json
    application.state.long_term = mem
    application.state.reload_mcp = lambda: {"connected": {}}
    return application


@pytest.mark.asyncio
async def test_skills_list_and_patch(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/skills")
        assert res.status_code == 200
        skills = res.json()["skills"]
        assert any(s["id"] == "demo" for s in skills)

        res = await client.patch(
            "/api/skills/demo",
            json={"enabled": False, "scope": {"isGlobal": False, "selectedAgents": ["document_agent"]}},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["enabled"] is False
        assert body["scope"]["selectedAgents"] == ["document_agent"]


@pytest.mark.asyncio
async def test_memory_crud(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.post("/api/memory", json={"content": "喜欢绿茶", "kind": "note"})
        assert res.status_code == 200
        mid = res.json()["id"]

        res = await client.get("/api/memory/list")
        assert any(i["id"] == mid for i in res.json()["items"])

        res = await client.get("/api/memory", params={"q": "绿茶", "k": 3})
        assert res.status_code == 200

        res = await client.delete(f"/api/memory/{mid}")
        assert res.status_code == 200
        res = await client.get("/api/memory/list")
        assert all(i["id"] != mid for i in res.json()["items"])


@pytest.mark.asyncio
async def test_mcp_servers_put_get(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        payload = {
            "mcpServers": {
                "echo": {
                    "command": "python3",
                    "args": ["-c", "print('hi')"],
                    "enabled": True,
                }
            }
        }
        res = await client.put("/api/mcp/servers", json=payload)
        assert res.status_code == 200
        assert "connected" in res.json()
        res = await client.get("/api/mcp/servers")
        assert "echo" in res.json()["mcpServers"]


@pytest.mark.asyncio
async def test_mcp_servers_put_triggers_reload(app):
    calls: list[str] = []

    def _reload():
        calls.append("reload")
        return {"connected": {"echo": []}}

    app.state.reload_mcp = _reload
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.put(
            "/api/mcp/servers",
            json={"mcpServers": {"echo": {"command": "python3"}}},
        )
        assert res.status_code == 200
        assert calls == ["reload"]


@pytest.mark.asyncio
async def test_mcp_import_merge_and_duplicate_409(app):
    app.state.reload_mcp = lambda: {"connected": {}}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.put(
            "/api/mcp/servers",
            json={"mcpServers": {"echo": {"command": "python3"}}},
        )
        res = await client.post(
            "/api/mcp/import",
            json={
                "mcpServers": {
                    "playwright": {"url": "https://example.com/mcp"},
                }
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert "echo" in body["mcpServers"]
        assert body["mcpServers"]["playwright"]["url"] == "https://example.com/mcp"

        res = await client.post(
            "/api/mcp/import",
            json={"mcpServers": {"Echo": {"command": "other"}}},
        )
        assert res.status_code == 409
