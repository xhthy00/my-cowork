import httpx
import pytest

from app.main import create_app
from app.server.routes import browser as browser_routes


@pytest.mark.asyncio
async def test_browser_view_uses_agent_browser_without_launching(monkeypatch):
    class Browser:
        def state(self):
            return {"open": False, "status": "closed", "url": "", "title": ""}

        def screenshot_data_url(self):
            return {"open": False, "image": ""}

    monkeypatch.setattr(browser_routes, "_BROWSER", Browser())
    app = create_app(task_manager=object())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/browser/state")).json()["open"] is False
        assert (await client.get("/api/browser/screenshot")).json()["image"] == ""
