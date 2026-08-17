"""Pending overlay write tracking for copy/worktree modes (local, no Control Server)."""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.workspace.paths import overlays_path, project_workdir_root
from app.workspace.resolver import WorkspaceStore, refresh_project_workdir

logger = logging.getLogger("workspace_overlay")


@dataclass
class OverlayEntry:
    id: str
    space_id: str
    project_id: str
    source_path: str  # absolute path under project workdir
    relative_path: str  # path relative to workdir / Space root
    created_at: str
    base_snapshot_id: str | None = None


def should_record_overlay(workdir_mode: str | None) -> bool:
    return workdir_mode in {"copy", "worktree"}


class OverlayStore:
    def _load(self, space_id: str, project_id: str) -> list[dict[str, Any]]:
        path = overlays_path(space_id, project_id)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return list(data.get("overlays") or [])
        except Exception:
            logger.warning("Failed to read overlays: %s", path)
            return []

    def _save(self, space_id: str, project_id: str, rows: list[dict[str, Any]]) -> None:
        path = overlays_path(space_id, project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"overlays": rows}, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)

    def list_overlays(self, space_id: str, project_id: str) -> list[OverlayEntry]:
        return [OverlayEntry(**row) for row in self._load(space_id, project_id)]

    def record_overlay_write(
        self,
        *,
        space_id: str,
        project_id: str,
        absolute_path: Path,
        base_snapshot_id: str | None = None,
    ) -> OverlayEntry | None:
        workdir = project_workdir_root(space_id, project_id).resolve()
        try:
            resolved = absolute_path.expanduser().resolve()
            rel = resolved.relative_to(workdir)
        except ValueError:
            return None

        rows = self._load(space_id, project_id)
        rel_s = rel.as_posix()
        # Upsert by relative path
        rows = [r for r in rows if r.get("relative_path") != rel_s]
        entry = OverlayEntry(
            id=f"ov_{uuid4().hex[:12]}",
            space_id=space_id,
            project_id=project_id,
            source_path=str(resolved),
            relative_path=rel_s,
            created_at=datetime.now(UTC).isoformat(),
            base_snapshot_id=base_snapshot_id,
        )
        rows.append(asdict(entry))
        self._save(space_id, project_id, rows)
        return entry

    def discard_overlays(
        self, space_id: str, project_id: str, overlay_ids: list[str] | None = None
    ) -> int:
        rows = self._load(space_id, project_id)
        if overlay_ids is None:
            count = len(rows)
            self._save(space_id, project_id, [])
            return count
        id_set = set(overlay_ids)
        kept = [r for r in rows if r.get("id") not in id_set]
        removed = len(rows) - len(kept)
        self._save(space_id, project_id, kept)
        return removed

    def apply_overlays(
        self,
        space_id: str,
        project_id: str,
        overlay_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        store = WorkspaceStore()
        binding = store.get_binding(space_id)
        if binding is None:
            raise ValueError("Space is not bound to a folder")
        space_root = Path(binding.workspace_root).expanduser().resolve()
        if not space_root.is_dir():
            raise ValueError("Bound Space root is not a directory")

        rows = self._load(space_id, project_id)
        if overlay_ids is not None:
            id_set = set(overlay_ids)
            to_apply = [r for r in rows if r.get("id") in id_set]
            remaining = [r for r in rows if r.get("id") not in id_set]
        else:
            to_apply = list(rows)
            remaining = []

        applied: list[str] = []
        errors: list[str] = []
        for row in to_apply:
            src = Path(row["source_path"])
            rel = row["relative_path"]
            dest = space_root / rel
            try:
                if not src.is_file():
                    errors.append(f"missing source: {src}")
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                applied.append(rel)
            except OSError as exc:
                errors.append(f"{rel}: {exc}")

        self._save(space_id, project_id, remaining)
        return {"applied": applied, "errors": errors, "remaining": len(remaining)}


_overlay_store: OverlayStore | None = None


def get_overlay_store() -> OverlayStore:
    global _overlay_store
    if _overlay_store is None:
        _overlay_store = OverlayStore()
    return _overlay_store


def maybe_record_write(absolute_path: Path) -> None:
    """Hook for fs.write — record overlay when runtime is copy/worktree."""
    from app.runtime.workspace_context import get_workspace_runtime

    rt = get_workspace_runtime()
    if rt is None or not should_record_overlay(rt.workdir_mode):
        return
    # Skip writes under task_output_root
    try:
        absolute_path.resolve().relative_to(rt.task_output_root.resolve())
        return
    except ValueError:
        pass
    get_overlay_store().record_overlay_write(
        space_id=rt.space_id,
        project_id=rt.project_id,
        absolute_path=absolute_path,
        base_snapshot_id=rt.base_snapshot_id,
    )


# Re-export refresh for API routes
__all__ = [
    "OverlayEntry",
    "OverlayStore",
    "get_overlay_store",
    "maybe_record_write",
    "refresh_project_workdir",
    "should_record_overlay",
]
