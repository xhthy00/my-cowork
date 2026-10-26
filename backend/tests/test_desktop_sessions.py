"""Desktop history survives backend restart and can import localStorage data."""

import httpx
import pytest

from app.main import create_app
from app.server.desktop_sessions import DesktopSessionStore


@pytest.mark.asyncio
async def test_desktop_snapshot_round_trip_across_store_instances(tmp_path):
    db = tmp_path / "sessions.db"
    app = create_app(task_manager=object())
    app.state.desktop_sessions = DesktopSessionStore(db)
    snapshot = {
        "sessions": [{"id": "s-1", "title": "报价方案", "status": "done"}],
        "activeId": "s-1",
        "messagesById": {"s-1": [{"id": "m-1", "role": "user", "content": "做报价方案"}]},
        "spaces": [{"id": "space-local", "name": "本地工作区", "sourceType": "blank", "rootPath": None}],
        "activeSpaceId": "space-local",
    }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.put("/api/desktop/sessions", json=snapshot)
        assert response.status_code == 200
    app.state.desktop_sessions.close()

    app.state.desktop_sessions = DesktopSessionStore(db)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/desktop/sessions")
        assert response.json()["snapshot"] == snapshot
    app.state.desktop_sessions.close()


@pytest.mark.asyncio
async def test_removed_desktop_sessions_cancel_only_their_background_runs(tmp_path):
    from unittest.mock import Mock
    manager = Mock()
    app = create_app(task_manager=manager)
    store = DesktopSessionStore(tmp_path / 'sessions.db')
    app.state.desktop_sessions = store
    store.save({'sessions': [{'id': 'keep'}, {'id': 'delete-a'}, {'id': 'delete-b'}]})
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.put('/api/desktop/sessions', json={'sessions': [{'id': 'keep'}]})
            assert response.status_code == 200
            assert {call.args[0] for call in manager.cancel_session.call_args_list} == {'delete-a', 'delete-b'}
            manager.cancel_session.reset_mock()
            await client.put('/api/desktop/sessions', json={'sessions': [{'id': 'keep', 'title': 'renamed'}]})
            manager.cancel_session.assert_not_called()
    finally:
        store.close()
