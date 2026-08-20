"""Dual-runtime switch: MY_COWORK_RUNTIME=v1|v2 (default v2 after goldens harness)."""

from __future__ import annotations

import os


def runtime_version() -> str:
    raw = (os.environ.get("MY_COWORK_RUNTIME") or "v2").strip().lower()
    return "v1" if raw in {"v1", "1", "legacy"} else "v2"


def is_v2() -> bool:
    return runtime_version() == "v2"
