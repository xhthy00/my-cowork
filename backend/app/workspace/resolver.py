"""Space binding + freeze task directories — adapted from eigent workspace_resolver.

Local-only: no Hands/deployment gate. Owner key is always ``local``.
``worktree`` shares the ``copy`` path (matches Eigent Brain today).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from app.workspace.paths import (
    OWNER,
    project_workdir_root,
    run_output_root,
    scratch_space_root,
    workspace_state_root,
)

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

logger = logging.getLogger("workspace_resolver")

BindingSource = Literal["space_local", "default"]
WORKDIR_MARKER = ".my-cowork-workdir.json"
COPY_IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".next",
    ".cache",
    "__pycache__",
}
MAX_COPY_FILE_SIZE = 25 * 1024 * 1024

WorkdirMode = Literal["direct-write", "copy", "worktree", "artifact-only"]
VALID_MODES = frozenset({"direct-write", "copy", "worktree", "artifact-only"})


@contextmanager
def _filesystem_space_lock(source_root: Path):
    if fcntl is None:
        yield
        return
    fd: int | None = None
    try:
        fd = os.open(source_root, os.O_RDONLY)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)


def _same_workspace_path(left: str, right: str) -> bool:
    try:
        return Path(left).expanduser().resolve() == Path(right).expanduser().resolve()
    except (OSError, RuntimeError):
        return False


def _folder_fingerprint(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "kind": "local_folder",
        "path": str(path),
        "device": stat.st_dev,
        "inode": stat.st_ino,
        "mtime_ns": getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1e9)),
        "ctime_ns": getattr(stat, "st_ctime_ns", int(stat.st_ctime * 1e9)),
    }


def _read_workdir_marker(workdir: Path) -> dict[str, Any] | None:
    marker = workdir / WORKDIR_MARKER
    if not marker.exists():
        return None
    try:
        return json.loads(marker.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Failed to read Project workdir marker: %s", marker)
        return None


def _copy_tree_limited(source_root: Path, target_root: Path) -> None:
    target_root.mkdir(parents=True, exist_ok=True)
    for item in source_root.iterdir():
        if item.name in COPY_IGNORE_DIRS or item.name == WORKDIR_MARKER:
            continue
        target = target_root / item.name
        try:
            if item.is_symlink():
                continue
            if item.is_dir():
                _copy_tree_limited(item, target)
                continue
            if item.is_file() and item.stat().st_size <= MAX_COPY_FILE_SIZE:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
        except OSError:
            logger.warning(
                "Failed to copy Space baseline item into Project workdir: %s",
                item,
                exc_info=True,
            )


def _copy_space_baseline(source_root: Path, workdir: Path) -> str:
    with _filesystem_space_lock(source_root):
        existing_marker = _read_workdir_marker(workdir)
        if existing_marker and existing_marker.get("base_snapshot_id"):
            return str(existing_marker["base_snapshot_id"])

        workdir.mkdir(parents=True, exist_ok=True)
        _copy_tree_limited(source_root, workdir)

        base_snapshot_id = f"snapshot_{uuid4().hex}"
        marker = workdir / WORKDIR_MARKER
        marker.write_text(
            json.dumps(
                {
                    "base_snapshot_id": base_snapshot_id,
                    "source_root": str(source_root),
                    "created_at": datetime.now(UTC).isoformat(),
                    "copy_ignore_dirs": sorted(COPY_IGNORE_DIRS),
                    "max_copy_file_size": MAX_COPY_FILE_SIZE,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return base_snapshot_id


def refresh_project_workdir(space_id: str, project_id: str) -> str:
    """Delete and re-copy project workdir from the bound Space root."""
    store = WorkspaceStore()
    binding = store.get_binding(space_id)
    if binding is None:
        raise ValueError("Space is not bound to a folder")
    source_root = Path(binding.workspace_root).expanduser().resolve()
    if not source_root.is_dir():
        raise ValueError("Bound Space root is not a directory")
    workdir = project_workdir_root(space_id, project_id)
    if workdir.exists():
        shutil.rmtree(workdir)
    return _copy_space_baseline(source_root, workdir)


@dataclass(frozen=True)
class WorkspaceBinding:
    space_id: str
    workspace_root: str
    source: str
    created_at: str
    updated_at: str
    root_fingerprint: dict[str, Any] | None = None
    version: int = 2


@dataclass(frozen=True)
class TaskSnapshot:
    task_id: str
    project_id: str
    space_id: str
    working_directory: str
    task_output_root: str
    binding_source: BindingSource
    created_at: str
    workdir_mode: str | None = None
    base_snapshot_id: str | None = None
    version: int = 2


@dataclass(frozen=True)
class FrozenTaskDirectories:
    working_directory: Path
    task_output_root: Path
    binding_source: BindingSource
    workdir_mode: str
    base_snapshot_id: str | None
    space_root: Path | None
    snapshot: TaskSnapshot


class WorkspaceStore:
    def __init__(self, owner: str = OWNER) -> None:
        self.owner = owner

    def _spaces_dir(self) -> Path:
        return workspace_state_root(self.owner) / "spaces"

    def _tasks_dir(self) -> Path:
        return workspace_state_root(self.owner) / "tasks"

    def _space_path(self, space_id: str) -> Path:
        return self._spaces_dir() / f"{space_id}.json"

    def _task_path(self, task_id: str) -> Path:
        return self._tasks_dir() / f"{task_id}.json"

    @staticmethod
    def _atomic_write(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(path)

    def get_binding(self, space_id: str) -> WorkspaceBinding | None:
        path = self._space_path(space_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return WorkspaceBinding(**data)
        except Exception:
            logger.warning("Failed to read workspace binding: %s", path)
            return None

    def save_binding(
        self,
        space_id: str,
        workspace_root: str,
        *,
        root_fingerprint: dict[str, Any] | None = None,
    ) -> WorkspaceBinding:
        now = datetime.now(UTC).isoformat()
        existing = self.get_binding(space_id)
        binding = WorkspaceBinding(
            space_id=space_id,
            workspace_root=workspace_root,
            source="space_local",
            created_at=existing.created_at if existing else now,
            updated_at=now,
            root_fingerprint=root_fingerprint,
        )
        self._atomic_write(self._space_path(space_id), asdict(binding))
        return binding

    def delete_binding(self, space_id: str) -> None:
        path = self._space_path(space_id)
        if path.exists():
            path.unlink()

    def list_bindings(self) -> list[WorkspaceBinding]:
        root = self._spaces_dir()
        if not root.exists():
            return []
        out: list[WorkspaceBinding] = []
        for path in sorted(root.glob("*.json")):
            try:
                out.append(WorkspaceBinding(**json.loads(path.read_text(encoding="utf-8"))))
            except Exception:
                logger.warning("Failed to read binding: %s", path)
        return out

    def write_snapshot(self, snapshot: TaskSnapshot) -> None:
        self._atomic_write(self._task_path(snapshot.task_id), asdict(snapshot))

    def get_snapshot(self, task_id: str) -> TaskSnapshot | None:
        path = self._task_path(task_id)
        if not path.exists():
            return None
        try:
            return TaskSnapshot(**json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return None


class WorkspaceResolver:
    def __init__(self, store: WorkspaceStore | None = None) -> None:
        self.store = store or WorkspaceStore()

    def ensure_space_binding(self, space_id: str, root_path: str) -> WorkspaceBinding:
        resolved = Path(root_path).expanduser().resolve()
        if not resolved.exists() or not resolved.is_dir():
            raise ValueError("Space root_path is not a readable directory")

        # One folder → one Space
        for other in self.store.list_bindings():
            if other.space_id == space_id:
                continue
            if _same_workspace_path(other.workspace_root, str(resolved)):
                raise ValueError(
                    f"Folder already bound to Space {other.space_id}"
                )

        existing = self.store.get_binding(space_id)
        if existing is not None:
            if _same_workspace_path(existing.workspace_root, str(resolved)):
                return existing
            raise ValueError("Space is already bound to a different folder")

        return self.store.save_binding(
            space_id,
            str(resolved),
            root_fingerprint=_folder_fingerprint(resolved),
        )

    def ensure_scratch_binding(self, space_id: str) -> WorkspaceBinding:
        root = scratch_space_root(space_id)
        root.mkdir(parents=True, exist_ok=True)
        existing = self.store.get_binding(space_id)
        if existing and _same_workspace_path(existing.workspace_root, str(root)):
            return existing
        if existing:
            self.store.delete_binding(space_id)
        return self.store.save_binding(
            space_id,
            str(root.resolve()),
            root_fingerprint=_folder_fingerprint(root),
        )

    def freeze_task_directories(
        self,
        *,
        space_id: str,
        project_id: str,
        task_id: str,
        workdir_mode: str | None = None,
        space_root_path: str | None = None,
    ) -> FrozenTaskDirectories:
        if space_root_path:
            self.ensure_space_binding(space_id, space_root_path)

        mode = workdir_mode if workdir_mode in VALID_MODES else None
        binding = self.store.get_binding(space_id)

        if binding and Path(binding.workspace_root).expanduser().is_dir():
            source_root = Path(binding.workspace_root).expanduser().resolve()
            task_output = run_output_root(space_id, project_id, task_id)
            task_output.mkdir(parents=True, exist_ok=True)
            resolved_mode = mode or "direct-write"

            if resolved_mode == "artifact-only":
                working_directory = task_output
                base_snapshot_id = None
            elif resolved_mode == "direct-write":
                working_directory = source_root
                base_snapshot_id = None
            else:
                # copy + worktree share limited tree copy
                working_directory = project_workdir_root(space_id, project_id)
                base_snapshot_id = _copy_space_baseline(source_root, working_directory)

            binding_source: BindingSource = "space_local"
            space_root: Path | None = source_root
        else:
            # No binding: scratch run dir (artifact-only semantics)
            resolved_mode = mode or "artifact-only"
            working_directory = run_output_root(space_id, project_id, task_id)
            working_directory.mkdir(parents=True, exist_ok=True)
            task_output = working_directory
            binding_source = "default"
            base_snapshot_id = None
            space_root = None

        snapshot = TaskSnapshot(
            task_id=task_id,
            project_id=project_id,
            space_id=space_id,
            working_directory=str(working_directory),
            task_output_root=str(task_output),
            binding_source=binding_source,
            created_at=datetime.now(UTC).isoformat(),
            workdir_mode=resolved_mode,
            base_snapshot_id=base_snapshot_id,
        )
        self.store.write_snapshot(snapshot)
        return FrozenTaskDirectories(
            working_directory=working_directory,
            task_output_root=task_output,
            binding_source=binding_source,
            workdir_mode=resolved_mode,
            base_snapshot_id=base_snapshot_id,
            space_root=space_root,
            snapshot=snapshot,
        )


_resolver: WorkspaceResolver | None = None


def get_workspace_resolver() -> WorkspaceResolver:
    global _resolver
    if _resolver is None:
        _resolver = WorkspaceResolver()
    return _resolver
