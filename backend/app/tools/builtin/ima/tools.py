"""LangChain tools for reading Tencent IMA knowledge bases."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.tools.builtin.ima.client import ImaClient, ImaError
from app.tools.builtin.ima.content import load_media_content
from app.tools.builtin.ima.wiki import (
    extract_library_entries,
    get_knowledge_base,
    get_knowledge_list,
    list_visible_knowledge_bases,
    search_knowledge,
)


_HIDE_IDS = (
    "When answering the user, cite knowledge-base names and item titles; "
    "do not read out knowledge_base_id, media_id, or folder_id."
)
_TERM_SPLIT = re.compile(r"[/／、，,|;；\n]+")
_BODY_FALLBACK_CAP = 40
_FOLDER_DEPTH_CAP = 5


def _dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _err(exc: Exception) -> str:
    return f"[ERROR] {exc}"


def split_search_terms(query: str) -> list[str]:
    """Split user queries like「涉密 / 系统集成 / 资质」into IMA-safe keywords."""
    raw = (query or "").strip()
    if not raw:
        return []
    parts: list[str] = []
    for chunk in _TERM_SPLIT.split(raw):
        chunk = chunk.strip()
        if not chunk:
            continue
        if " " in chunk or "\t" in chunk:
            parts.extend(t for t in chunk.split() if t.strip())
        else:
            parts.append(chunk)
    seen: set[str] = set()
    terms: list[str] = []
    for term in parts:
        if len(term) < 2 or term in seen:
            continue
        seen.add(term)
        terms.append(term)
        if len(terms) >= 4:
            break
    return terms or [raw]


def _search_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows, _, _ = extract_library_entries(data)
    out: list[dict[str, Any]] = []
    for row in rows:
        mid = str(row.get("media_id") or row.get("folder_id") or "").strip()
        if not mid and not row.get("title"):
            continue
        out.append(
            {
                "kind": row.get("kind") or "file",
                "media_id": mid,
                "title": row.get("title") or "",
                "parent_folder_id": row.get("parent_folder_id") or "",
                "highlight_content": row.get("highlight_content") or "",
            }
        )
    return out


def _snippet(hay: str, term: str, radius: int = 40) -> str:
    idx = hay.find(term)
    if idx < 0:
        return hay[:160]
    start = max(0, idx - radius)
    return hay[start : start + 160].strip()


async def _iter_library_files(
    client: ImaClient,
    knowledge_base_id: str,
    *,
    folder_id: str | None = None,
    depth: int = 0,
    scanned: list[int],
) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    cursor = ""
    while scanned[0] < _BODY_FALLBACK_CAP:
        listed = await get_knowledge_list(
            client,
            knowledge_base_id=knowledge_base_id,
            cursor=cursor,
            limit=50,
            folder_id=folder_id,
        )
        entries, is_end, next_cursor = extract_library_entries(listed)
        for entry in entries:
            if scanned[0] >= _BODY_FALLBACK_CAP:
                break
            if entry.get("kind") == "folder":
                if depth >= _FOLDER_DEPTH_CAP:
                    continue
                nested = await _iter_library_files(
                    client,
                    knowledge_base_id,
                    folder_id=str(entry.get("folder_id") or "") or None,
                    depth=depth + 1,
                    scanned=scanned,
                )
                files.extend(nested)
                continue
            scanned[0] += 1
            files.append(entry)
        if is_end or not next_cursor:
            break
        cursor = next_cursor
    return files


async def _body_fallback_search(
    client: ImaClient,
    *,
    terms: list[str],
    knowledge_base_id: str,
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    files = await _iter_library_files(
        client, knowledge_base_id, folder_id=None, depth=0, scanned=[0]
    )
    for item in files:
        mid = str(item.get("media_id") or "").strip()
        if not mid:
            continue
        title = str(item.get("title") or "")
        try:
            media = await load_media_content(client, mid, max_chars=20_000)
        except (ImaError, OSError):
            text = ""
        else:
            text = str(media.get("content") or "")
        hay = f"{title}\n{text}"
        matched = next((term for term in terms if term and term in hay), "")
        if not matched:
            continue
        hits.append(
            {
                "kind": "file",
                "media_id": mid,
                "title": title,
                "parent_folder_id": item.get("parent_folder_id") or "",
                "highlight_content": _snippet(hay, matched),
            }
        )
    return hits


class ListBasesArgs(BaseModel):
    query: str = Field(
        default="",
        description="Knowledge-base name keyword. Empty string lists all bases.",
    )
    cursor: str = Field(default="", description="Pagination cursor; first page is empty.")
    limit: int = Field(default=20, description="Page size 1-20")


class GetBaseArgs(BaseModel):
    knowledge_base_id: str = Field(description="Knowledge base id from ima_list_knowledge_bases")


class ListKnowledgeArgs(BaseModel):
    knowledge_base_id: str = Field(description="Knowledge base id")
    folder_id: str = Field(
        default="",
        description="Optional folder id (starts with folder_). Omit for root.",
    )
    cursor: str = Field(default="", description="Pagination cursor; first page is empty.")
    limit: int = Field(default=20, description="Page size 1-50")


class SearchKnowledgeArgs(BaseModel):
    query: str = Field(description="Search keywords inside a knowledge base")
    knowledge_base_id: str = Field(description="Knowledge base id")
    cursor: str = Field(default="", description="Pagination cursor; first page is empty.")


class GetMediaArgs(BaseModel):
    media_id: str = Field(description="media_id from ima_search_knowledge or ima_list_knowledge")
    max_chars: int = Field(default=12000, description="Max characters of extracted text")


async def ima_list_knowledge_bases(
    query: str = "",
    cursor: str = "",
    limit: int = 20,
) -> str:
    try:
        payload = await list_visible_knowledge_bases(
            ImaClient(), query=query, cursor=cursor, limit=limit
        )
    except ImaError as exc:
        return _err(exc)
    return _dumps(payload)


async def ima_get_knowledge_base(knowledge_base_id: str) -> str:
    kid = (knowledge_base_id or "").strip()
    if not kid:
        return "[ERROR] knowledge_base_id 不能为空"
    try:
        data = await get_knowledge_base(ImaClient(), [kid])
    except ImaError as exc:
        return _err(exc)
    infos = data.get("infos") if isinstance(data.get("infos"), dict) else {}
    info = infos.get(kid) or {}
    return _dumps(info if info else {"id": kid, "infos": infos})


async def ima_list_knowledge(
    knowledge_base_id: str,
    folder_id: str = "",
    cursor: str = "",
    limit: int = 20,
) -> str:
    kid = (knowledge_base_id or "").strip()
    if not kid:
        return "[ERROR] knowledge_base_id 不能为空"
    try:
        data = await get_knowledge_list(
            ImaClient(),
            knowledge_base_id=kid,
            cursor=cursor,
            limit=limit,
            folder_id=(folder_id or "").strip() or None,
        )
    except ImaError as exc:
        return _err(exc)
    entries, is_end, next_cursor = extract_library_entries(data)
    files = [e for e in entries if e.get("kind") != "folder"]
    folders = [e for e in entries if e.get("kind") == "folder"]
    return _dumps(
        {
            "files": files,
            "folders": folders,
            "knowledge_list": entries,
            "current_path": data.get("current_path") or data.get("currentPath") or [],
            "is_end": is_end,
            "next_cursor": next_cursor,
            "note": (
                "folders must be opened with ima_list_knowledge(folder_id). "
                "A search question does not need downloads."
            ),
        }
    )


async def ima_search_knowledge(
    query: str,
    knowledge_base_id: str,
    cursor: str = "",
) -> str:
    q = (query or "").strip()
    kid = (knowledge_base_id or "").strip()
    if not q:
        return "[ERROR] query 不能为空"
    if not kid:
        return "[ERROR] knowledge_base_id 不能为空"
    terms = split_search_terms(q)
    client = ImaClient()
    try:
        merged: dict[str, dict[str, Any]] = {}
        last_end, last_cursor = True, ""
        for term in terms:
            page_cursor = cursor
            while True:
                data = await search_knowledge(
                    client, query=term, knowledge_base_id=kid, cursor=page_cursor
                )
                last_end, last_cursor = True, ""
                if isinstance(data, dict):
                    last_end = bool(data.get("is_end", data.get("isEnd", True)))
                    last_cursor = str(data.get("next_cursor") or data.get("nextCursor") or "")
                for row in _search_rows(data):
                    merged.setdefault(str(row.get("media_id") or row.get("title")), row)
                if last_end or not last_cursor or last_cursor == page_cursor:
                    break
                page_cursor = last_cursor
        rows = list(merged.values())
        note = (
            "Hits are titles + short clips only. Next: ima_get_media_content "
            "on the top items, then summarize 要点 for the user. "
            "Do not download, curl, bash, fs_write, or create notes."
        )
        source = "ima"
        if not rows and not (cursor or "").strip():
            rows = await _body_fallback_search(client, terms=terms, knowledge_base_id=kid)
            if rows:
                source = "body"
                note = (
                    "Title search was empty; these hits include body clips. "
                    "Still call ima_get_media_content for enough text, then summarize. "
                    "Do not download files."
                )
            else:
                note = (
                    "No hits. You may ima_list_knowledge to browse folders. "
                    "Do not download files."
                )
        payload: dict[str, Any] = {
            "items": rows,
            "is_end": last_end if source == "ima" else True,
            "next_cursor": last_cursor if source == "ima" else "",
            "note": note,
        }
        if len(terms) > 1:
            payload["terms"] = terms
        if source == "body":
            payload["source"] = "body"
    except ImaError as exc:
        return _err(exc)
    return _dumps(payload)


async def ima_get_media_content(media_id: str, max_chars: int = 12000) -> str:
    mid = (media_id or "").strip()
    if not mid:
        return "[ERROR] media_id 不能为空"
    try:
        data = await load_media_content(ImaClient(), mid, max_chars=max_chars)
    except ImaError as exc:
        return _err(exc)
    except OSError as exc:
        return _err(exc)
    return _dumps(data)


def make_ima_tools() -> list[StructuredTool]:
    return [
        StructuredTool.from_function(
            coroutine=ima_list_knowledge_bases,
            name="ima_list_knowledge_bases",
            description=(
                "List or search Tencent IMA knowledge bases by name. "
                "Use query='' to list all. Returns {id,name}. "
                + _HIDE_IDS
            ),
            args_schema=ListBasesArgs,
        ),
        StructuredTool.from_function(
            coroutine=ima_get_knowledge_base,
            name="ima_get_knowledge_base",
            description=(
                "Get IMA knowledge-base details (name, description, recommended questions). "
                + _HIDE_IDS
            ),
            args_schema=GetBaseArgs,
        ),
        StructuredTool.from_function(
            coroutine=ima_list_knowledge,
            name="ima_list_knowledge",
            description=(
                "Browse files and folders in an IMA knowledge base. "
                "Pass folder_id (prefix folder_) to enter a subfolder. "
                + _HIDE_IDS
            ),
            args_schema=ListKnowledgeArgs,
        ),
        StructuredTool.from_function(
            coroutine=ima_search_knowledge,
            name="ima_search_knowledge",
            description=(
                "Search documents inside one IMA knowledge base. "
                "Returns titles and short highlight clips — not a full answer. "
                "Then call ima_get_media_content and summarize. Do not download files. "
                + _HIDE_IDS
            ),
            args_schema=SearchKnowledgeArgs,
        ),
        StructuredTool.from_function(
            coroutine=ima_get_media_content,
            name="ima_get_media_content",
            description=(
                "Extract plaintext of one IMA item by media_id (docx/html/notes). "
                "Use after search so you can summarize; content is already text. "
                "Do not curl the url, save to disk, or tell the user a file was downloaded. "
                + _HIDE_IDS
            ),
            args_schema=GetMediaArgs,
        ),
    ]
