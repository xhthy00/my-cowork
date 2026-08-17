"""Tests for LocalhostOnlyMiddleware."""

import httpx
import pytest
from fastapi import FastAPI

from app.main import create_app
from unittest.mock import MagicMock


@pytest.fixture()
def app() -> FastAPI:
    return create_app(task_manager=MagicMock(), bus=None, confirm_hub=MagicMock())


@pytest.mark.asyncio
async def test_remote_non_webhook_returns_403(app: FastAPI):
    transport = httpx.ASGITransport(app=app, client=("8.8.8.8", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/health")
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_loopback_non_webhook_ok(app: FastAPI):
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/health")
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_remote_webhook_not_blocked_by_localhost_middleware(app: FastAPI):
    """Webhook path is reachable from remote (IP/signature checked in route)."""
    transport = httpx.ASGITransport(app=app, client=("8.8.8.8", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/webhook/lark",
            json={"type": "url_verification", "challenge": "abc"},
        )
    assert res.status_code == 200
    assert res.json()["challenge"] == "abc"
