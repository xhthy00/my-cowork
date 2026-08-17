"""Workspace path formulas — adapted from eigent workspace_paths.py.

Root: ~/.my-cowork (override via MY_COWORK_DATA_DIR). Single-user desktop uses
owner key ``local``.
"""

from __future__ import annotations

import os
from pathlib import Path

OWNER = "local"


def data_root() -> Path:
    raw = os.environ.get("MY_COWORK_DATA_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".my-cowork").resolve()


def workspace_state_root(owner: str = OWNER) -> Path:
    return data_root() / "workspaces" / owner


def run_output_root(
    space_id: str,
    project_id: str,
    run_id: str,
    owner: str = OWNER,
) -> Path:
    return (
        data_root()
        / "spaces"
        / space_id
        / "projects"
        / project_id
        / "runs"
        / run_id
    )


def project_workdir_root(
    space_id: str,
    project_id: str,
    owner: str = OWNER,
) -> Path:
    return (
        data_root()
        / "spaces"
        / space_id
        / "projects"
        / project_id
        / "workdir"
    )


def overlays_path(space_id: str, project_id: str, owner: str = OWNER) -> Path:
    return (
        data_root()
        / "spaces"
        / space_id
        / "projects"
        / project_id
        / "overlays.json"
    )


def scratch_space_root(space_id: str, owner: str = OWNER) -> Path:
    """Blank Space filesystem root under the data dir."""
    return data_root() / "spaces" / space_id / "scratch"
