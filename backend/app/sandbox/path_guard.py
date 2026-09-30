"""Path whitelist sandbox with per-instance state.

The module also exposes a default global instance via the legacy
``set_whitelist`` / ``check_path`` / ``add_whitelist`` functions for
backward compatibility. New code should instantiate ``PathGuard`` directly.
"""

import json
from collections.abc import Callable
from pathlib import Path
from threading import Lock

_DESKTOP_ALIASES = {"desktop", "桌面"}


def _is_remote_or_unc_path(raw: str) -> bool:
    """True for http(s)/file URLs and Windows UNC / protocol-relative network paths."""
    s = (raw or "").strip()
    lower = s.lower()
    if lower.startswith(("http://", "https://", "file://")):
        return True
    if s.startswith(("\\\\?\\", "\\\\.\\")):
        return False
    if s.startswith("\\\\"):
        return True
    if s.startswith("//"):
        host = s[2:].split("/")[0].split("\\")[0]
        return "." in host
    return False


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
    if _is_remote_or_unc_path(raw):
        raise PathGuardError(
            "Remote/UNC paths are not allowed. IMA documents must be fetched with ima_get_media_content."
        )

    expanded = Path(raw).expanduser()

    # Bare desktop directory aliases
    if expanded.as_posix() in ("Desktop", "桌面") or raw in ("~/Desktop", "~/桌面"):
        return desktop_dir()

    if expanded.is_absolute():
        return expanded.resolve()

    parts = list(expanded.parts)
    for i, part in enumerate(parts):
        if part.lower() in _DESKTOP_ALIASES or part == "桌面":
            rest = parts[i + 1 :]
            return desktop_dir().joinpath(*rest).resolve()

    root = base if base is not None else Path.home()
    return (root / expanded).resolve()


def resolve_tool_path(path: str) -> Path:
    """Normalize using frozen working_directory when a WorkspaceRuntime is active."""
    base: Path | None = None
    try:
        from app.task_support.workspace_context import get_workspace_runtime

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
        from app.task_support.workspace_context import get_workspace_runtime

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

    def __init__(self, paths: list[str] | None = None, *, config_path: Path | None = None,
                 workspace_paths: Callable[[], list[str]] | None = None,
                 read_only_paths: list[str] | None = None) -> None:
        self._whitelist: set[str] = set()
        self._save_lock = Lock()
        self.config_path = config_path
        self._workspace_paths = workspace_paths or (lambda: [])
        self._read_only_paths = {str(Path(p).expanduser().resolve()) for p in (read_only_paths or [])}
        if paths is None and config_path is not None and config_path.exists():
            data = json.loads(config_path.read_text(encoding="utf-8"))
            paths = data["paths"]
            if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
                raise ValueError("Invalid saved directory permissions")
        if paths is not None:
            self.set_whitelist(paths)

    def get_whitelist(self) -> list[str]:
        return sorted(self._whitelist)

    def workspace_paths(self) -> list[str]:
        return sorted({str(Path(p).expanduser().resolve()) for p in self._workspace_paths()})

    def save_whitelist(self, paths: list[str]) -> None:
        normalized = []
        for raw in paths:
            p = Path(raw).expanduser()
            if not raw.strip() or not p.is_absolute() or _is_remote_or_unc_path(raw):
                raise ValueError("请输入本机目录的绝对路径，或使用 ~/ 开头的路径")
            if not p.is_dir():
                raise ValueError("目录不存在或不可访问")
            normalized.append(str(p.resolve()))
        if self.config_path is None:
            raise OSError("Directory permission storage is unavailable")
        with self._save_lock:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.config_path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"paths": sorted(set(normalized))}, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.config_path)
            self.set_whitelist(normalized)

    def set_whitelist(self, paths: list[str]) -> None:
        """Replace the whitelist with the provided absolute/relative paths."""
        self._whitelist = {str(Path(p).expanduser().resolve()) for p in paths}

    def add_whitelist(self, path: str) -> None:
        """Add a path to the whitelist."""
        self._whitelist.add(str(Path(path).expanduser().resolve()))

    def check_path(self, path: str, *, read_only: bool = False) -> None:
        """Raise PathGuardError if *path* is not inside any whitelisted directory."""
        resolved = resolve_tool_path(path)
        allowed_paths = self._whitelist | set(self.workspace_paths())
        if read_only:
            allowed_paths |= self._read_only_paths
        # Generated task output is available only to the current task. A direct
        # user workspace still needs an active binding or explicit permission.
        from app.task_support.workspace_context import get_workspace_runtime
        rt = get_workspace_runtime()
        if rt is not None:
            allowed_paths.add(str(rt.task_output_root.resolve()))
            if rt.space_root is None or rt.working_directory.resolve() != rt.space_root.resolve():
                allowed_paths.add(str(rt.working_directory.resolve()))
        for allowed in allowed_paths:
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
