"""Explicit long-term memory actions exposed to the agent."""

from __future__ import annotations

from typing import Any, Callable

from langchain_core.tools import BaseTool, tool

from .long_term import LongTermStore
from .scoped import project_memory_key
from .settings import MemorySettings


def make_memory_tools(
    store: LongTermStore, settings: MemorySettings,
    runtime_getter: Callable[[], Any] | None = None,
) -> list[BaseTool]:
    get_runtime = runtime_getter or (lambda: None)

    def workspace_key() -> str | None:
        runtime = get_runtime()
        if runtime is None:
            return None
        return project_memory_key(runtime.memory_root, runtime.project_id)

    def announce(item: dict, previous: str = "") -> None:
        runtime = get_runtime()
        if runtime is None or runtime.bus is None:
            return
        try:
            runtime.bus.emit({"type": "memory.saved", "task_id": runtime.task_id,
                              "payload": {"id": item["id"], "scope": item["scope"],
                                          "content": item["content"], "previous": previous}})
        except Exception:
            pass

    @tool
    def remember(content: str, summary: str = "", scope: str = "workspace") -> dict:
        """Save a durable fact for future sessions. Use global for user preferences,
        workspace for project facts. Check existing memory IDs before adding duplicates.
        """
        if not settings.enabled:
            return {"saved": False, "error": "记忆写入已关闭；本次对话可使用，但不会保存到未来会话。"}
        try:
            item = store.remember(content, scope=scope,
                                  workspace=workspace_key() if scope == "workspace" else None,
                                  summary=summary)
        except ValueError as exc:
            return {"saved": False, "error": str(exc)}
        announce(item)
        return {"saved": True, "id": item["id"], "scope": item["scope"]}

    @tool
    def memory_read(memory_ids: list[int]) -> dict:
        """Read full saved memories by ID when the prompt shows only summaries."""
        visible = {int(row["id"]) for row in store.list_memories(workspace=workspace_key())}
        found = [store.get_memory(mid) for mid in memory_ids if mid in visible]
        return {"memories": [item for item in found if item is not None],
                "missing": [mid for mid in memory_ids if mid not in visible]}

    @tool
    def memory_update(memory_id: int, content: str, summary: str = "") -> dict:
        """Replace an existing saved memory by ID with corrected content."""
        if not settings.enabled:
            return {"updated": False, "error": "记忆写入已关闭"}
        visible = {int(row["id"]) for row in store.list_memories(workspace=workspace_key())}
        if memory_id not in visible:
            return {"updated": False, "error": "记忆不存在或不属于当前项目"}
        previous = store.get_memory(memory_id)
        try:
            item = store.update_memory(memory_id, content, summary=summary)
        except ValueError as exc:
            return {"updated": False, "error": str(exc)}
        if item is None:
            return {"updated": False, "error": "记忆不存在"}
        announce(item, str(previous["content"]) if previous else "")
        return {"updated": True, "id": memory_id}

    @tool
    def memory_forget(memory_id: int) -> dict:
        """Delete a saved memory that is wrong or obsolete."""
        if not settings.enabled:
            return {"deleted": False, "error": "记忆写入已关闭"}
        visible = {int(row["id"]) for row in store.list_memories(workspace=workspace_key())}
        return {"deleted": store.forget_memory(memory_id) if memory_id in visible else False}

    return [remember, memory_read, memory_update, memory_forget]
