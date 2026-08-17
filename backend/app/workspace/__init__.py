"""Local Space/Project workspace binding (adapted from Eigent Brain)."""

from app.workspace.resolver import (
    FrozenTaskDirectories,
    WorkspaceBinding,
    WorkspaceResolver,
    WorkspaceStore,
    get_workspace_resolver,
)

__all__ = [
    "FrozenTaskDirectories",
    "WorkspaceBinding",
    "WorkspaceResolver",
    "WorkspaceStore",
    "get_workspace_resolver",
]
