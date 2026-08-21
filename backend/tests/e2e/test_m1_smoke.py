import pytest

from app.main import build_stack, create_app
from tests.conftest import FakeChatModel, make_ai


def _auto_approve_all(confirm_hub):
    def _auto_approve(event: dict) -> None:
        if event.get("type") == "tool.confirm_request":
            confirm_hub.resolve(event["call_id"], True)
        if event.get("type") == "to_sub_tasks":
            confirm_hub.resolve_plan(
                event.get("task_id") or "",
                event.get("subtasks") or [],
            )

    return _auto_approve


class TestM1Smoke:
    @pytest.mark.asyncio
    async def test_chat_writes_file_end_to_end(self, tmp_path):
        target_path = tmp_path / "hello.txt"

        # planner_llm used by decompose_subtasks
        planner = FakeChatModel(
            responses=[
                make_ai(
                    content=(
                        '[{"id":"task_1","content":"写 hello.txt 内容 hi",'
                        '"assignee":"developer_agent","dependencies":[]}]'
                    )
                ),
            ]
        )
        developer = FakeChatModel(
            responses=[
                make_ai(
                    content="",
                    tool_calls=[
                        {
                            "name": "fs_write",
                            "args": {"path": str(target_path), "content": "hi"},
                            "id": "call_1",
                        }
                    ],
                ),
                make_ai(content="File written successfully."),
            ]
        )
        idle = FakeChatModel(responses=[make_ai(content="ok")])

        stack = build_stack(
            supervisor_llm=planner,
            file_worker_llm=developer,
            doc_worker_llm=idle,
            web_worker_llm=idle,
            msg_worker_llm=idle,
            whitelist=[str(tmp_path)],
        )
        task_manager = stack["task_manager"]
        bus = stack["bus"]
        confirm_hub = stack["confirm_hub"]
        bus.subscribe(_auto_approve_all(confirm_hub))
        app = create_app(task_manager=task_manager, bus=bus, confirm_hub=confirm_hub)

        import httpx

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            async with client.stream(
                "POST",
                "/api/chat",
                json={
                    "text": "写 hello.txt 内容 hi",
                    "session_mode": "workforce",
                },
            ) as response:
                chunks = []
                async for chunk in response.aiter_text():
                    chunks.append(chunk)

        body = "".join(chunks)
        assert "graph.end" in body
        assert "to_sub_tasks" in body
        assert target_path.exists()
        assert target_path.read_text() == "hi"

    @pytest.mark.asyncio
    async def test_single_agent_writes_file_end_to_end(self, tmp_path):
        """Eigent Single Agent path: one meta-agent with full tools, no routing."""
        target_path = tmp_path / "solo.txt"

        single_model = FakeChatModel(
            responses=[
                make_ai(
                    content="",
                    tool_calls=[
                        {
                            "name": "fs_write",
                            "args": {"path": str(target_path), "content": "solo"},
                            "id": "call_sa",
                        }
                    ],
                ),
                make_ai(content="Written by Single Agent."),
            ]
        )
        idle = FakeChatModel(responses=[make_ai(content="ok")])

        stack = build_stack(
            supervisor_llm=single_model,
            file_worker_llm=idle,
            doc_worker_llm=idle,
            web_worker_llm=idle,
            msg_worker_llm=idle,
            whitelist=[str(tmp_path)],
        )
        task_manager = stack["task_manager"]
        bus = stack["bus"]
        confirm_hub = stack["confirm_hub"]
        bus.subscribe(_auto_approve_all(confirm_hub))
        app = create_app(task_manager=task_manager, bus=bus, confirm_hub=confirm_hub)

        import httpx

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            async with client.stream(
                "POST",
                "/api/chat",
                json={
                    "text": "写 solo.txt 内容 solo",
                    "session_mode": "single-agent",
                },
            ) as response:
                chunks = []
                async for chunk in response.aiter_text():
                    chunks.append(chunk)

        body = "".join(chunks)
        assert "graph.end" in body
        assert '"agent_id":"single_agent"' in body.replace(" ", "")
        assert target_path.exists()
        assert target_path.read_text() == "solo"
