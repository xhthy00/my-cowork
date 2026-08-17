import asyncio

import pytest

from app.guardrails.approval import ConfirmHub, ConfirmTimeout


class TestConfirmHub:
    @pytest.mark.asyncio
    async def test_emits_confirm_request_event(self) -> None:
        events = []
        hub = ConfirmHub(emit=events.append, timeout_seconds=0.1)

        task = asyncio.create_task(
            hub.request("c1", "fs.write", {"path": "/tmp/a.txt"})
        )
        await asyncio.sleep(0)

        assert len(events) == 1
        assert events[0]["type"] == "tool.confirm_request"
        assert events[0]["call_id"] == "c1"
        assert events[0]["tool"] == "fs.write"

        hub.resolve("c1", True)
        assert await task is True

    @pytest.mark.asyncio
    async def test_resolve_true_approves(self) -> None:
        hub = ConfirmHub(timeout_seconds=0.1)

        task = asyncio.create_task(hub.request("c1", "fs.write", {"path": "/tmp/a.txt"}))
        await asyncio.sleep(0)
        hub.resolve("c1", True)

        assert await task is True

    @pytest.mark.asyncio
    async def test_resolve_false_rejects(self) -> None:
        hub = ConfirmHub(timeout_seconds=0.1)

        task = asyncio.create_task(hub.request("c2", "exec.bash", {"cmd": "ls"}))
        await asyncio.sleep(0)
        hub.resolve("c2", False)

        assert await task is False

    @pytest.mark.asyncio
    async def test_timeout_raises_confirm_timeout(self) -> None:
        hub = ConfirmHub(timeout_seconds=0.01)

        with pytest.raises(ConfirmTimeout):
            await hub.request("c3", "fs.write", {"path": "/tmp/a.txt"})

    @pytest.mark.asyncio
    async def test_multiple_requests_isolated(self) -> None:
        hub = ConfirmHub(timeout_seconds=0.1)

        t1 = asyncio.create_task(hub.request("c1", "fs.write", {}))
        t2 = asyncio.create_task(hub.request("c2", "exec.bash", {}))
        await asyncio.sleep(0)

        hub.resolve("c1", True)
        hub.resolve("c2", False)

        assert await t1 is True
        assert await t2 is False

    @pytest.mark.asyncio
    async def test_resolve_after_timeout_is_ignored(self) -> None:
        hub = ConfirmHub(timeout_seconds=0.01)

        with pytest.raises(ConfirmTimeout):
            await hub.request("c1", "fs.write", {})

        # Should not raise; the future is gone.
        assert hub.resolve("c1", True) is False

    @pytest.mark.asyncio
    async def test_resolve_returns_true_when_pending(self) -> None:
        hub = ConfirmHub(timeout_seconds=0.1)
        task = asyncio.create_task(hub.request("c1", "fs.write", {}))
        await asyncio.sleep(0)
        assert hub.resolve("c1", True) is True
        assert await task is True
        assert hub.resolve("c1", True) is False

    @pytest.mark.asyncio
    async def test_plan_confirm_roundtrip(self) -> None:
        events = []
        hub = ConfirmHub(emit=events.append, timeout_seconds=0.5)
        task = asyncio.create_task(
            hub.request_plan(
                "tid",
                [{"id": "task_1", "content": "x", "assignee": "browser_agent"}],
            )
        )
        await asyncio.sleep(0)
        assert events[0]["type"] == "to_sub_tasks"
        edited = [
            {
                "id": "task_1",
                "content": "edited",
                "assignee": "document_agent",
                "dependencies": [],
            }
        ]
        hub.resolve_plan("tid", edited)
        result = await task
        assert result[0]["content"] == "edited"
