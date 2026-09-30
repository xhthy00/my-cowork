"""Non-blocking OS locks survive neither a crash nor a stale PID file."""
from __future__ import annotations

import os
from pathlib import Path

from .snapshots import managed


class FileLock:
    def __init__(self, root: Path, name: str):
        self.path = managed(root, name + ".lock")
        self.file = None

    def acquire(self):
        if self.file is not None:
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        file = self.path.open("a+b")
        try:
            file.seek(0, 2)
            if not file.tell():
                file.write(b"0")
                file.flush()
            file.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            file.close()
            raise RuntimeError("应用数据正被另一进程使用，请关闭对应实例后重试") from exc
        self.file = file
        return self

    def close(self):
        if self.file is not None:
            self.file.close()
            self.file = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *_):
        self.close()
