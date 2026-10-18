"""A fresh installation must boot the real backend and harness without a model."""
from pathlib import Path

import httpx
import pytest

from app.main import create_app


@pytest.mark.asyncio
async def test_first_launch_without_model_or_api_key(monkeypatch, tmp_path):
    for name in (
        "MY_COWORK_API_KEY", "MY_COWORK_PROVIDER", "MY_COWORK_MODEL",
        "MY_COWORK_BASE_URL", "MY_COWORK_FALLBACK", "MY_COWORK_OPERATION_TOKEN",
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MY_COWORK_ENABLE_SCHEDULER", "0")
    monkeypatch.setenv("MY_COWORK_CHANNEL_AUTOSTART", "0")
    monkeypatch.setenv("MY_COWORK_SKILLS_ROOT", str(tmp_path / "skills"))
    monkeypatch.setenv("MY_COWORK_SKILLS_CONFIG", str(tmp_path / "skills.json"))
    monkeypatch.setenv("MY_COWORK_INDUSTRY_TOKEN", "first-launch-test-token")

    app = create_app()
    runtime = app.state.task_manager.runtime
    # Assembly and lifespan must share a thread, as in production, because the
    # capability broker owns a thread-bound SQLite connection.
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1",
            headers={"X-MyCowork-Industry-Token": "first-launch-test-token"},
        ) as client:
            assert (await client.get("/health")).json() == {"status": "ok"}
            assert (await client.get("/api/industry-apps/runtime")).status_code == 200
        assert not app.state.admission.paused
        assert runtime.process is not None
        assert runtime.process.returncode is None
        assert (Path(runtime.data_dir) / "harness" / "checkpoints.db").is_file()
    assert runtime.process is None
