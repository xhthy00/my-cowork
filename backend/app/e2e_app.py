"""E2E entrypoint: FastAPI app with a scripted fake LLM for fs.write.

Started by Electron when ``MY_COWORK_UVICORN_APP=app.e2e_app:app``.
Writes to ``MY_COWORK_E2E_PATH`` (default ``~/Desktop/hello.txt``).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from app.main import build_stack, create_app


class _FakeChatModel(BaseChatModel):
    responses: list[BaseMessage] = Field(default_factory=list)
    idx: int = 0

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_FakeChatModel":
        return self

    def _generate(
        self,
        messages: Sequence[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        if self.idx >= len(self.responses):
            raise RuntimeError("FakeChatModel exhausted its scripted responses")
        message = self.responses[self.idx]
        self.idx += 1
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(
        self,
        messages: Sequence[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)

    @property
    def _llm_type(self) -> str:
        return "fake-e2e"


def _target_path() -> Path:
    raw = os.environ.get("MY_COWORK_E2E_PATH")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / "Desktop" / "hello.txt"


def create_e2e_app():
    target = _target_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    content = os.environ.get("MY_COWORK_E2E_CONTENT", "hi")

    planner = _FakeChatModel(
        responses=[
            AIMessage(
                content=(
                    '[{"id":"task_1","content":"write hello.txt",'
                    '"assignee":"developer_agent","dependencies":[]}]'
                )
            ),
        ]
    )
    developer = _FakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "fs_write",
                        "args": {"path": str(target), "content": content},
                        "id": "call_e2e_1",
                    }
                ],
            ),
            AIMessage(content="File written successfully."),
        ]
    )
    idle = _FakeChatModel(responses=[AIMessage(content="ok")])

    stack = build_stack(
        supervisor_llm=planner,
        file_worker_llm=developer,
        doc_worker_llm=idle,
        web_worker_llm=idle,
        msg_worker_llm=idle,
        whitelist=[str(target.parent), str(Path.home())],
    )
    bus = stack["bus"]
    confirm_hub = stack["confirm_hub"]

    def _auto(event: dict) -> None:
        if event.get("type") == "tool.confirm_request":
            confirm_hub.resolve(event["call_id"], True)
        if event.get("type") == "to_sub_tasks":
            confirm_hub.resolve_plan(
                event.get("task_id") or "",
                event.get("subtasks") or [],
            )

    bus.subscribe(_auto)
    return create_app(
        task_manager=stack["task_manager"],
        bus=bus,
        confirm_hub=confirm_hub,
    )


app = create_e2e_app()
