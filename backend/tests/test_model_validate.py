from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.main import create_app


class TestModelValidateRoute:
    @pytest.mark.asyncio
    async def test_validate_success(self):
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value=MagicMock())
        app = create_app(task_manager=MagicMock(), bus=None, confirm_hub=MagicMock())

        with patch("app.server.routes.model.gateway.create_model", return_value=llm) as create:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/model/validate",
                    json={
                        "provider": "openai_compat",
                        "model": "gpt-4o-mini",
                        "api_key": "sk-test",
                        "base_url": "https://openrouter.ai/api/v1",
                    },
                )

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["error"] is None
        assert isinstance(body["latency_ms"], int)
        create.assert_called_once()
        llm.ainvoke.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_validate_failure(self):
        llm = MagicMock()
        llm.ainvoke = AsyncMock(side_effect=RuntimeError("bad key"))
        app = create_app(task_manager=MagicMock(), bus=None, confirm_hub=MagicMock())

        with patch("app.server.routes.model.gateway.create_model", return_value=llm):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/model/validate",
                    json={
                        "provider": "anthropic",
                        "model": "claude-sonnet-4-20250514",
                        "api_key": "sk-bad",
                    },
                )

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is False
        assert "bad key" in (body["error"] or "")

    @pytest.mark.asyncio
    async def test_validate_unknown_provider(self):
        app = create_app(task_manager=MagicMock(), bus=None, confirm_hub=MagicMock())
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/model/validate",
                json={"provider": "nope", "model": "x", "api_key": "k"},
            )
        assert response.status_code == 200
        assert response.json()["ok"] is False
