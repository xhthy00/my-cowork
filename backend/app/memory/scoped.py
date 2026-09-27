"""OpenWorker-style project identity and bounded prompt rendering."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

INDEX_THRESHOLD_CHARS = 8_000
INDEX_FULL_NEWEST = 10


def project_memory_key(root: str | None, project_id: str | None = None) -> str | None:
    if root:
        path = Path(root).expanduser().resolve()
        if path.is_dir():
            try:
                result = subprocess.run(
                    ["git", "-C", str(path), "rev-parse", "--git-common-dir"],
                    capture_output=True, text=True, timeout=5, check=False,
                )
                if result.returncode == 0 and result.stdout.strip():
                    common = Path(result.stdout.strip())
                    if not common.is_absolute():
                        common = path / common
                    common = common.resolve()
                    return str(common.parent if common.name == ".git" else common)
            except (OSError, subprocess.TimeoutExpired):
                pass
        return str(path)
    return f"project:{project_id}" if project_id else None


def render_memories(items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    ordered = sorted(items, key=lambda item: int(item["id"]))
    full = "已知长期记忆（来自之前的会话）：\n" + "\n".join(
        f"- [#{item['id']}] {item['content']}" for item in ordered
    )
    if len(full) <= INDEX_THRESHOLD_CHARS:
        return full
    newest = {int(item["id"]) for item in ordered[-INDEX_FULL_NEWEST:]}
    lines: list[str] = []
    for item in ordered:
        if int(item["id"]) in newest:
            body = str(item["content"])
        else:
            body = str(item.get("summary") or "").strip()
            if not body:
                body = str(item["content"]).splitlines()[0][:80]
        lines.append(f"- [#{item['id']}] {body}")
    return ("已知长期记忆（来自之前的会话）：\n" + "\n".join(lines)
            + "\n较早的条目仅显示摘要；在依据它行动前，请用 memory_read 读取完整内容。")
