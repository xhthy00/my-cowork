"""SkillHub marketplace proxy: list mapping, install, upstream/SSRF/size errors."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest
import respx

from app.main import create_app
from app.memory.long_term import LongTermStore
from app.skills.config import save_skills_config
from app.skills.skillhub import (
    MAX_ZIP_BYTES,
    SkillHubError,
    assert_allowed_url,
    download_hub_skill,
    normalize_skill,
)


class FakeTaskManager:
    async def handle(self, req):
        if False:
            yield {}


def _zip_skill(slug: str = "demo-skill") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            f"{slug}/SKILL.md",
            f"---\nname: {slug}\ndescription: from hub\n---\n\n# {slug}\n",
        )
    return buf.getvalue()


HUB_ITEM = {
    "name": "编程专家.Skill",
    "description": "en desc",
    "description_zh": "中文描述",
    "iconUrl": "https://example.com/icon.png",
    "downloads": 435385,
    "stars": 26,
    "category": "dev-programming",
    "slug": "dev-expert",
    "version": "1.0.48",
    "homepage": "https://api.skillhub.cn/user_741dc82b/dev-expert",
    "ownerName": "user_741dc82b",
    "labels": {"requires_api_key": "false"},
    "namespace": {
        "canonicalName": "@user_741dc82b/dev-expert",
        "handle": "user_741dc82b",
        "publicSlug": "dev-expert",
    },
}


@pytest.fixture()
def app(tmp_path: Path):
    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    cfg = tmp_path / "skills-config.json"
    save_skills_config({"version": 1, "skills": {}}, cfg)
    mcp_json = tmp_path / "mcp.json"
    mcp_json.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    application = create_app(task_manager=FakeTaskManager(), bus=None)
    application.state.skills_root = skills_root
    application.state.skills_config_path = cfg
    application.state.mcp_json_path = mcp_json
    application.state.long_term = LongTermStore(tmp_path / "memory.db")
    application.state.reload_mcp = lambda: {"connected": {}}
    return application


def test_normalize_skill_prefers_zh_and_handle():
    got = normalize_skill(HUB_ITEM)
    assert got is not None
    assert got["name"] == "编程专家.Skill"
    assert got["description"] == "中文描述"
    assert got["slug"] == "dev-expert"
    assert got["handle"] == "user_741dc82b"
    assert got["downloads"] == 435385
    assert got["stars"] == 26
    assert got["requiresApiKey"] is False
    assert got["iconUrl"] == "https://example.com/icon.png"


def test_assert_allowed_url_blocks_ssrf_host():
    with pytest.raises(SkillHubError, match="blocked"):
        assert_allowed_url("http://127.0.0.1/evil", base="https://api.skillhub.cn")
    with pytest.raises(SkillHubError, match="blocked"):
        assert_allowed_url("https://evil.example/x", base="https://api.skillhub.cn")
    assert_allowed_url("https://api.skillhub.cn/api/v1/download", base="https://api.skillhub.cn")
    assert_allowed_url(
        "https://skillhub-1388575217.cos.accelerate.myqcloud.com/skills/a.zip",
        base="https://api.skillhub.cn",
    )


@pytest.mark.asyncio
@respx.mock
async def test_hub_list_maps_fields(app):
    respx.get(url__regex=r"https://api\.skillhub\.cn/api/skills.*").mock(
        return_value=httpx.Response(
            200,
            json={"code": 0, "data": {"skills": [HUB_ITEM], "total": 9}, "message": "success"},
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get(
            "/api/skillhub",
            params={"keyword": "pdf", "category": "dev-programming", "sortBy": "score", "page": 1, "pageSize": 12},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 9
    skill = body["skills"][0]
    assert skill["slug"] == "dev-expert"
    assert skill["handle"] == "user_741dc82b"
    assert skill["description"] == "中文描述"
    req = respx.calls.last.request
    assert "keyword=pdf" in str(req.url)
    assert "category=dev-programming" in str(req.url)
    assert "sortBy=score" in str(req.url)


@pytest.mark.asyncio
async def test_nested_skills_hub_path_is_method_not_allowed(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/skills/hub")
    assert res.status_code == 405


@pytest.mark.asyncio
@respx.mock
async def test_hub_list_upstream_500(app):
    respx.get(url__regex=r"https://api\.skillhub\.cn/api/skills.*").mock(
        return_value=httpx.Response(503, text="down")
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/skillhub")
    assert res.status_code == 502


@pytest.mark.asyncio
@respx.mock
async def test_hub_install_writes_skill_md(app):
    zip_bytes = _zip_skill("hub-demo")
    respx.get(url__regex=r"https://api\.skillhub\.cn/api/v1/download.*").mock(
        return_value=httpx.Response(200, content=zip_bytes, headers={"Content-Type": "application/zip"})
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.post(
            "/api/skillhub/install",
            json={"handle": "user_741dc82b", "slug": "hub-demo"},
        )
    assert res.status_code == 200
    assert res.json()["id"] == "hub-demo"
    root = Path(app.state.skills_root)
    assert (root / "hub-demo" / "SKILL.md").is_file()


@pytest.mark.asyncio
@respx.mock
async def test_hub_install_redirect_to_evil_blocked(app):
    respx.get(url__regex=r"https://api\.skillhub\.cn/api/v1/download.*").mock(
        return_value=httpx.Response(302, headers={"Location": "http://127.0.0.1/steal"})
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.post(
            "/api/skillhub/install",
            json={"handle": "user_x", "slug": "demo"},
        )
    assert res.status_code == 400
    assert "blocked" in res.json()["detail"]


@pytest.mark.asyncio
@respx.mock
async def test_hub_install_rejects_oversized_zip():
    respx.get(url__regex=r"https://api\.skillhub\.cn/api/v1/download.*").mock(
        return_value=httpx.Response(
            200,
            content=b"PK" + b"x" * 100,
            headers={"Content-Length": str(MAX_ZIP_BYTES + 1), "Content-Type": "application/zip"},
        )
    )
    with pytest.raises(SkillHubError, match="too large"):
        async with httpx.AsyncClient() as http:
            await download_hub_skill("user_x", "demo", client=http)


@pytest.mark.asyncio
async def test_hub_install_rejects_invalid_handle(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.post(
            "/api/skillhub/install",
            json={"handle": "../etc", "slug": "demo"},
        )
    assert res.status_code == 400
