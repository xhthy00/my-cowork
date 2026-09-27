"""Agent-facing human question tool, adapted from Eigent HumanToolkit."""

from __future__ import annotations

from typing import Literal

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from app.guardrails.human_input import HumanInputHub
from app.runtime.todo_context import get_current_agent_id, get_todo_runtime


class HumanQuestionField(BaseModel):
    label: str = Field(description="A short question or field label in the user's language")
    kind: Literal["single", "multiple", "text"] = Field(description="Single choice, multiple choice, or free text")
    options: list[str] = Field(default_factory=list, description="Short choices for single/multiple fields")
    required: bool = Field(default=False, description="Whether this answer is necessary to continue")
    placeholder: str = Field(default="", description="Brief example for a text answer")


def make_ask_human_tool(hub: HumanInputHub) -> BaseTool:
    @tool
    async def ask_human(
        question: str,
        options: list[str] | None = None,
        fields: list[HumanQuestionField] | None = None,
    ) -> str:
        """Ask the user when essential information is missing or a meaningful
        choice has multiple viable options. Wait for their answer before acting.
        For several details, use fields so the UI shows a short form card.
        Give concise options when helpful; every choice also allows a custom answer.
        Do not use this for facts available through tools or routine choices.
        """
        runtime = get_todo_runtime()
        if runtime is None:
            return "[ERROR] No active task is available for a user question."
        return await hub.ask(
            runtime.task_id,
            get_current_agent_id() or runtime.agent_id,
            question,
            options,
            [field.model_dump() for field in fields] if fields else None,
        )

    return ask_human
