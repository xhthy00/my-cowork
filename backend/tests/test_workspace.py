"""Tests for Space workspace freeze (four workdir modes) + overlays."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.workspace.overlay import OverlayStore, maybe_record_write
from app.workspace.resolver import WorkspaceResolver, WorkspaceStore
from app.runtime.workspace_context import (
    WorkspaceRuntime,
    reset_workspace_runtime,
    set_workspace_runtime,
)


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("MY_COWORK_DATA_DIR", str(root))
    # Reset singleton-ish modules that cache paths via env
    import app.workspace.resolver as resolver_mod
    import app.workspace.overlay as overlay_mod

    resolver_mod._resolver = None
    overlay_mod._overlay_store = None
    return root


def test_direct_write_freeze(data_dir: Path, tmp_path: Path) -> None:
    folder = tmp_path / "user-folder"
    folder.mkdir()
    (folder / "a.txt").write_text("hello", encoding="utf-8")

    resolver = WorkspaceResolver(WorkspaceStore())
    resolver.ensure_space_binding("space-1", str(folder))
    frozen = resolver.freeze_task_directories(
        space_id="space-1",
        project_id="proj-1",
        task_id="task-1",
        workdir_mode="direct-write",
    )
    assert frozen.working_directory == folder.resolve()
    assert frozen.task_output_root.exists()
    assert frozen.workdir_mode == "direct-write"
    assert frozen.base_snapshot_id is None


def test_artifact_only_freeze(data_dir: Path, tmp_path: Path) -> None:
    folder = tmp_path / "user-folder"
    folder.mkdir()
    resolver = WorkspaceResolver(WorkspaceStore())
    resolver.ensure_space_binding("space-2", str(folder))
    frozen = resolver.freeze_task_directories(
        space_id="space-2",
        project_id="proj-2",
        task_id="task-2",
        workdir_mode="artifact-only",
    )
    assert frozen.working_directory == frozen.task_output_root
    assert folder.resolve() not in (
        frozen.working_directory,
        frozen.working_directory.resolve(),
    ) or frozen.working_directory != folder.resolve()
    assert frozen.working_directory != folder.resolve()


def test_copy_and_worktree_share_path(data_dir: Path, tmp_path: Path) -> None:
    folder = tmp_path / "user-folder"
    folder.mkdir()
    (folder / "src.txt").write_text("x", encoding="utf-8")
    resolver = WorkspaceResolver(WorkspaceStore())
    resolver.ensure_space_binding("space-3", str(folder))

    frozen_copy = resolver.freeze_task_directories(
        space_id="space-3",
        project_id="proj-3",
        task_id="task-c",
        workdir_mode="copy",
    )
    assert (frozen_copy.working_directory / "src.txt").read_text(encoding="utf-8") == "x"
    assert frozen_copy.base_snapshot_id

    frozen_wt = resolver.freeze_task_directories(
        space_id="space-3",
        project_id="proj-3",
        task_id="task-w",
        workdir_mode="worktree",
    )
    # Same project workdir; marker reused
    assert frozen_wt.working_directory == frozen_copy.working_directory
    assert frozen_wt.base_snapshot_id == frozen_copy.base_snapshot_id


def test_no_binding_falls_back_to_run_dir(data_dir: Path) -> None:
    resolver = WorkspaceResolver(WorkspaceStore())
    frozen = resolver.freeze_task_directories(
        space_id="space-blank",
        project_id="proj-b",
        task_id="task-b",
        workdir_mode="artifact-only",
    )
    assert frozen.binding_source == "default"
    assert frozen.working_directory == frozen.task_output_root
    assert frozen.working_directory.exists()


def test_overlay_apply(data_dir: Path, tmp_path: Path) -> None:
    folder = tmp_path / "user-folder"
    folder.mkdir()
    (folder / "src.txt").write_text("orig", encoding="utf-8")

    resolver = WorkspaceResolver(WorkspaceStore())
    resolver.ensure_space_binding("space-ov", str(folder))
    frozen = resolver.freeze_task_directories(
        space_id="space-ov",
        project_id="proj-ov",
        task_id="task-ov",
        workdir_mode="copy",
    )
    edited = frozen.working_directory / "src.txt"
    edited.write_text("edited", encoding="utf-8")

    token = set_workspace_runtime(
        WorkspaceRuntime(
            space_id="space-ov",
            project_id="proj-ov",
            task_id="task-ov",
            working_directory=frozen.working_directory,
            task_output_root=frozen.task_output_root,
            workdir_mode="copy",
            base_snapshot_id=frozen.base_snapshot_id,
            space_root=folder.resolve(),
        )
    )
    try:
        maybe_record_write(edited)
    finally:
        reset_workspace_runtime(token)

    store = OverlayStore()
    rows = store.list_overlays("space-ov", "proj-ov")
    assert len(rows) == 1
    result = store.apply_overlays("space-ov", "proj-ov")
    assert result["applied"] == ["src.txt"]
    assert (folder / "src.txt").read_text(encoding="utf-8") == "edited"
    assert store.list_overlays("space-ov", "proj-ov") == []


def test_duplicate_folder_bind_rejected(data_dir: Path, tmp_path: Path) -> None:
    folder = tmp_path / "shared"
    folder.mkdir()
    resolver = WorkspaceResolver(WorkspaceStore())
    resolver.ensure_space_binding("s-a", str(folder))
    with pytest.raises(ValueError, match="already bound"):
        resolver.ensure_space_binding("s-b", str(folder))
