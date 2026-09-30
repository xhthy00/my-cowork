"""Runtime context for frozen Space/Project directories (per task)."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import Path


@dataclass
class WorkspaceRuntime:
    space_id: str
    project_id: str
    task_id: str
    working_directory: Path
    task_output_root: Path
    workdir_mode: str
    base_snapshot_id: str | None = None
    space_root: Path | None = None


_workspace_runtime: ContextVar[WorkspaceRuntime | None] = ContextVar(
    "workspace_runtime", default=None
)


def set_workspace_runtime(runtime: WorkspaceRuntime) -> Token:
    return _workspace_runtime.set(runtime)


def reset_workspace_runtime(token: Token) -> None:
    _workspace_runtime.reset(token)


def get_workspace_runtime() -> WorkspaceRuntime | None:
    return _workspace_runtime.get()
