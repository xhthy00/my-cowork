"""Manage ``officecli watch`` subprocesses per file path."""

from __future__ import annotations

import re
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.tools.officecli.resolve import ERR_NOT_FOUND, resolve_officecli

ERR_START_FAILED = "START_FAILED"
ERR_PORT_TIMEOUT = "PORT_TIMEOUT"


def _pick_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        try:
            sock.connect(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _parse_already_running_port(err: str) -> int | None:
    """Extract port from officecli 'already running at http://host:PORT' stderr."""
    match = re.search(r"https?://(?:127\.0\.0\.1|localhost):(\d+)", err)
    if not match:
        return None
    port = int(match.group(1))
    return port if _port_open(port) else None


@dataclass
class _WatchEntry:
    path: str
    port: int
    process: subprocess.Popen[Any] | None
    url: str


class WatchManager:
    """Start/stop officecli watch servers keyed by absolute file path."""

    def __init__(self, *, ready_timeout: float = 30.0) -> None:
        self._ready_timeout = ready_timeout
        self._entries: dict[str, _WatchEntry] = {}

    def _alive(self, entry: _WatchEntry) -> bool:
        if entry.process is not None and entry.process.poll() is None:
            return True
        # External leftover (reused) — still valid while the port answers.
        return entry.process is None and _port_open(entry.port)

    def start(self, file_path: str) -> dict[str, Any]:
        path = str(Path(file_path).expanduser().resolve())
        existing = self._entries.get(path)
        if existing is not None and self._alive(existing):
            return {
                "status": "ready",
                "url": existing.url,
                "port": existing.port,
                "error_code": None,
            }
        if existing is not None:
            self._entries.pop(path, None)

        binary = resolve_officecli()
        if binary is None:
            return {
                "status": "error",
                "url": None,
                "port": None,
                "error_code": ERR_NOT_FOUND,
            }

        if not Path(path).is_file():
            return {
                "status": "error",
                "url": None,
                "port": None,
                "error_code": ERR_START_FAILED,
                "detail": f"file not found: {path}",
            }

        port = _pick_port()
        try:
            proc = subprocess.Popen(
                [str(binary), "watch", path, "--port", str(port)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            return {
                "status": "error",
                "url": None,
                "port": None,
                "error_code": ERR_START_FAILED,
                "detail": str(exc),
            }

        deadline = time.monotonic() + self._ready_timeout
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                err = ""
                if proc.stderr is not None:
                    err = proc.stderr.read()[-1000:]
                # Reuse leftover watch from a previous session.
                reused_port = _parse_already_running_port(err)
                if reused_port is not None:
                    url = f"http://127.0.0.1:{reused_port}/"
                    self._entries[path] = _WatchEntry(
                        path=path, port=reused_port, process=None, url=url
                    )
                    return {
                        "status": "ready",
                        "url": url,
                        "port": reused_port,
                        "error_code": None,
                    }
                return {
                    "status": "error",
                    "url": None,
                    "port": None,
                    "error_code": ERR_START_FAILED,
                    "detail": err or f"exit={proc.returncode}",
                }
            if _port_open(port):
                url = f"http://127.0.0.1:{port}/"
                self._entries[path] = _WatchEntry(
                    path=path, port=port, process=proc, url=url
                )
                return {
                    "status": "ready",
                    "url": url,
                    "port": port,
                    "error_code": None,
                }
            time.sleep(0.15)

        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        return {
            "status": "error",
            "url": None,
            "port": None,
            "error_code": ERR_PORT_TIMEOUT,
        }

    def stop(self, file_path: str) -> dict[str, Any]:
        path = str(Path(file_path).expanduser().resolve())
        entry = self._entries.pop(path, None)
        if entry is None:
            return {"status": "stopped"}
        if entry.process is not None and entry.process.poll() is None:
            entry.process.terminate()
            try:
                entry.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                entry.process.kill()
        return {"status": "stopped"}

    def stop_all(self) -> None:
        for path in list(self._entries):
            self.stop(path)
