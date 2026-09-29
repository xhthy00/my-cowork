"""Stable v1 contract for trusted in-process applications."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import APIRouter
from pydantic import BaseModel


@dataclass(frozen=True)
class AppContext:
    app_id: str
    data_root: Path

    def workspace_data_dir(self, workspace_id: str) -> Path:
        if not workspace_id or "/" in workspace_id or "\\" in workspace_id or workspace_id in {".", ".."}:
            raise ValueError("invalid workspace_id")
        path = self.data_root / workspace_id
        path.mkdir(parents=True, exist_ok=True)
        return path


@dataclass
class AppContribution:
    router: APIRouter
    tools: list["AppTool"] = field(default_factory=list)
    jobs: list[Any] = field(default_factory=list)


@dataclass(frozen=True)
class AppToolCallContext:
    """Host-owned execution identity; never supplied by the language model."""

    app_id: str
    space_id: str | None
    project_id: str | None
    task_id: str | None


@dataclass(frozen=True)
class AppTool:
    """A typed business operation supplied by a trusted application ZIP."""

    name: str
    title: str
    description: str
    args_schema: type[BaseModel]
    run: Callable[[AppToolCallContext, BaseModel], Any]
    access: Literal["read", "write"] = "read"


@dataclass(frozen=True)
class LoadedAppTool:
    app_id: str
    app_name: str
    tool: AppTool
