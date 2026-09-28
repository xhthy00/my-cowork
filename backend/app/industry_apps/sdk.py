"""Stable v1 contract for trusted in-process applications."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import APIRouter


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
    tools: list[Any] = field(default_factory=list)
    jobs: list[Any] = field(default_factory=list)
