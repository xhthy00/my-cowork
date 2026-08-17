from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import FastAPI

from app.main import create_app


class TestConfirmRoute:
    @pytest.mark.asyncio
    async def test_confirm_post_resolves_hub_with_true(self):
        hub = MagicMock()
        hub.resolve.return_value = True
        app = create_app(task_manager=MagicMock(), bus=None, confirm_hub=hub)

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/tool/confirm/c1", json={"ok": True})

        assert response.status_code == 200
        assert response.json()["resolved"] is True
        hub.resolve.assert_called_once_with("c1", True)

    @pytest.mark.asyncio
    async def test_confirm_post_resolves_hub_with_false(self):
        hub = MagicMock()
        hub.resolve.return_value = True
        app = create_app(task_manager=MagicMock(), bus=None, confirm_hub=hub)

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/tool/confirm/c2", json={"ok": False})

        assert response.status_code == 200
        assert response.json()["resolved"] is True
        hub.resolve.assert_called_once_with("c2", False)

    @pytest.mark.asyncio
    async def test_confirm_post_reports_unresolved(self):
        hub = MagicMock()
        hub.resolve.return_value = False
        app = create_app(task_manager=MagicMock(), bus=None, confirm_hub=hub)

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/tool/confirm/exec.bash%3Aabc", json={"ok": True}
            )

        assert response.status_code == 200
        assert response.json() == {"ok": True, "resolved": False}

    @pytest.mark.asyncio
    async def test_confirm_requires_ok_field(self):
        hub = MagicMock()
        app = create_app(task_manager=MagicMock(), bus=None, confirm_hub=hub)

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/tool/confirm/c1", json={})

        assert response.status_code == 422
        hub.resolve.assert_not_called()
