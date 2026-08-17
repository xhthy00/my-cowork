"""Command deny-list guardrail for shell execution tools."""

from __future__ import annotations

import re
from typing import Any


class CommandForbidden(Exception):
    """Raised when a shell command matches a forbidden pattern."""


DEFAULT_PATTERNS: list[str] = [
    # Wipe filesystem root or `/*` only. Do not match `rm -rf /Users/...` or `/tmp/...`.
    r"rm\s+-rf\s+['\"]?/(?:\*['\"]?|['\"]?(?:\s*[;&|`'\"]|$))",
    r"chmod\s+-R\s+777\s+/",
    r"dd\s+if=/dev/zero",
    r"mkfs.*",
]


class CommandFilter:
    """Check shell commands against a regex deny list.

    The default patterns block a small set of high-risk operations while
    allowing common development commands and scoped operations under ``/tmp``.
    """

    def __init__(
        self,
        patterns: list[str] | None = None,
        audit: Any = None,
    ) -> None:
        self._patterns = [re.compile(p) for p in (patterns or DEFAULT_PATTERNS)]
        self._audit = audit

    def check(self, cmd: str) -> None:
        """Raise ``CommandForbidden`` if *cmd* matches any forbidden pattern.

        Matching is done anywhere inside the command string so that commands
        wrapped in ``bash -c '...'`` are still caught.
        """
        for pattern in self._patterns:
            if pattern.search(cmd):
                if self._audit is not None:
                    try:
                        self._audit.log(
                            kind="command_forbidden",
                            tool="exec.bash",
                            detail={"cmd": cmd, "pattern": pattern.pattern},
                        )
                    except Exception:
                        pass
                raise CommandForbidden(
                    f"Command matches forbidden pattern: {pattern.pattern}"
                )
