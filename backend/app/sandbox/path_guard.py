"""Path whitelist sandbox with per-instance state.

The module also exposes a default global instance via the legacy
``set_whitelist`` / ``check_path`` / ``add_whitelist`` functions for
backward compatibility. New code should instantiate ``PathGuard`` directly.
"""

from pathlib import Path

_DESKTOP_ALIASES = {"desktop", "桌面"}


class PathGuardError(Exception):
    """Raised when an operation targets a path outside the allowed whitelist."""


def desktop_dir() -> Path:
    """Return the user's Desktop directory (``Desktop`` or ``桌面``)."""
    home = Path.home()
    for name in ("Desktop", "桌面"):
        candidate = home / name
        if candidate.is_dir():
            return candidate.resolve()
    return (home / "Desktop").resolve()


def normalize_user_path(path: str, *, base: Path | None = None) -> Path:
    """Map user/LLM path aliases to an absolute filesystem path.

    Models often emit relative junk like ``../Desktop/hello.txt`` (relative to
    the backend cwd). Treat Desktop/桌面 as the real user desktop, expand ``~``,
    and resolve other relative paths against *base* (frozen working_directory
    when set) or the home directory — never process cwd.
    """
    raw = (path or "").strip()
    if not raw:
        raise PathGuardError("Empty path")

    expanded = Path(raw).expanduser()

    # Bare desktop directory aliases
    if expanded.as_posix() in ("Desktop", "桌面") or raw in ("~/Desktop", "~/桌面"):
        return desktop_dir()

    parts = list(expanded.parts)
    for i, part in enumerate(parts):
        if part.lower() in _DESKTOP_ALIASES or part == "桌面":
            rest = parts[i + 1 :]
            return desktop_dir().joinpath(*rest).resolve()

    if expanded.is_absolute():
        return expanded.resolve()

    root = base if base is not None else Path.home()
    return (root / expanded).resolve()


def resolve_tool_path(path: str) -> Path:
    """Normalize using frozen working_directory when a WorkspaceRuntime is active."""
    base: Path | None = None
    try:
        from app.runtime.workspace_context import get_workspace_runtime

        rt = get_workspace_runtime()
        if rt is not None:
            base = rt.working_directory
    except Exception:
        base = None
    return normalize_user_path(path, base=base)


def resolve_write_path(path: str) -> Path:
    """Resolve a write target; remap Desktop → task working_directory when active.

    Reads still use :func:`resolve_tool_path` so existing Desktop files remain
    readable. New outputs during a workspace task land in the project workdir
    unless the path is already under that workdir / task_output_root.
    """
    resolved = resolve_tool_path(path)
    try:
        from app.runtime.workspace_context import get_workspace_runtime

        rt = get_workspace_runtime()
    except Exception:
        return resolved
    if rt is None:
        return resolved

    work = rt.working_directory.resolve()
    out = rt.task_output_root.resolve()
    try:
        if resolved == work or resolved.is_relative_to(work):
            return resolved
        if resolved == out or resolved.is_relative_to(out):
            return resolved
    except (ValueError, OSError):
        pass

    desk = desktop_dir()
    try:
        if resolved == desk or resolved.is_relative_to(desk):
            rel = (
                Path(".")
                if resolved == desk
                else resolved.relative_to(desk)
            )
            if rel == Path("."):
                return work
            return (work / rel).resolve()
    except (ValueError, OSError):
        pass
    return resolved


class PathGuard:
    """Filesystem path whitelist guard. Each instance holds its own whitelist."""

    def __init__(self, paths: list[str] | None = None) -> None:
        self._whitelist: set[str] = set()
        if paths:
            self.set_whitelist(paths)

    def set_whitelist(self, paths: list[str]) -> None:
        """Replace the whitelist with the provided absolute/relative paths."""
        self._whitelist = {str(Path(p).expanduser().resolve()) for p in paths}

    def add_whitelist(self, path: str) -> None:
        """Add a path to the whitelist."""
        self._whitelist.add(str(Path(path).expanduser().resolve()))

    def check_path(self, path: str) -> None:
        """Raise PathGuardError if *path* is not inside any whitelisted directory."""
        if not self._whitelist:
            raise PathGuardError("No whitelist configured")

        resolved = resolve_tool_path(path)

        for allowed in self._whitelist:
            allowed_path = Path(allowed)
            if resolved == allowed_path or resolved.is_relative_to(allowed_path):
                return

        raise PathGuardError(f"Path {resolved} is not in the whitelist")


# Legacy module-level default instance for backward compatibility.
_DEFAULT_GUARD = PathGuard()


def set_whitelist(paths: list[str]) -> None:
    """Set the whitelist on the default global ``PathGuard`` instance."""
    _DEFAULT_GUARD.set_whitelist(paths)


def add_whitelist(path: str) -> None:
    """Add a path to the default global ``PathGuard`` instance."""
    _DEFAULT_GUARD.add_whitelist(path)


def check_path(path: str) -> None:
    """Check a path against the default global ``PathGuard`` instance."""
    _DEFAULT_GUARD.check_path(path)
