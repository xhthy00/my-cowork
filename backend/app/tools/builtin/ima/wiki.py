"""IMA wiki v1 OpenAPI wrappers (official ima-skill contracts)."""

from __future__ import annotations

from typing import Any

from app.tools.builtin.ima.client import ImaClient, ImaError

_LIST_KEYS = (
    "info_list",
    "infoList",
    "addable_knowledge_base_list",
    "addableKnowledgeBaseList",
    "knowledge_base_list",
    "knowledgeBaseList",
    "list",
    "items",
)

EMPTY_KB_HINT = (
    "凭证已生效（空列表不是未配置 Key）。OpenAPI 未返回任何知识库。"
    "若 IMA 客户端里能看到内容：请确认生成 API Key 的微信/QQ 与客户端登录是同一账号；"
    "「笔记」不会出现在知识库接口里；团队/仅协作库有时对个人 OpenAPI 不可见。"
    "请在 IMA 客户端用同一账号打开 https://ima.qq.com/agent-interface 重新生成 Key，保存到 Hub 后再试。"
    "不要提示用户去 Hub 重新填写「未配置」的凭证。"
)


def _as_dict(data: Any, *, list_key: str = "info_list") -> dict[str, Any]:
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        return {list_key: data}
    return {}


def _list_from(data: dict[str, Any]) -> list[Any] | None:
    for key in _LIST_KEYS:
        val = data.get(key)
        if isinstance(val, list):
            return val
    return None


def extract_knowledge_bases(
    data: Any,
) -> tuple[list[dict[str, Any]], bool, str, list[str]]:
    """Normalize search/addable payloads. Returns rows, is_end, cursor, data_keys."""
    keys: list[str] = []
    payload: Any = data
    if isinstance(payload, dict):
        keys = [str(k) for k in payload.keys()]
        if _list_from(payload) is None:
            inner = payload.get("data")
            if isinstance(inner, list):
                payload = {"info_list": inner}
            elif isinstance(inner, dict):
                keys = [str(k) for k in inner.keys()]
                payload = inner
    if isinstance(payload, list):
        raw, is_end, next_cursor = payload, True, ""
    elif isinstance(payload, dict):
        raw = _list_from(payload) or []
        end_val = payload.get("is_end")
        if end_val is None:
            end_val = payload.get("isEnd", True)
        is_end = bool(end_val)
        next_cursor = str(
            payload.get("next_cursor") or payload.get("nextCursor") or ""
        )
    else:
        return [], True, "", keys
    rows: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kid = str(
            item.get("id")
            or item.get("kb_id")
            or item.get("kbId")
            or item.get("knowledge_base_id")
            or item.get("knowledgeBaseId")
            or ""
        ).strip()
        name = str(
            item.get("name") or item.get("kb_name") or item.get("kbName") or ""
        ).strip()
        if not kid and not name:
            continue
        rows.append(
            {
                "id": kid,
                "name": name,
                "cover_url": item.get("cover_url") or item.get("coverUrl") or "",
            }
        )
    return rows, is_end, next_cursor, keys


_ENTRY_LIST_KEYS = (
    "knowledge_list",
    "knowledgeList",
    "info_list",
    "infoList",
    "list",
    "items",
)


def _pagination(data: dict[str, Any]) -> tuple[bool, str]:
    end_val = data.get("is_end")
    if end_val is None:
        end_val = data.get("isEnd", True)
    nxt = str(data.get("next_cursor") or data.get("nextCursor") or "")
    return bool(end_val), nxt


def extract_library_entries(data: Any) -> tuple[list[dict[str, Any]], bool, str]:
    """Files and folders from get_knowledge_list / search_knowledge payloads."""
    if isinstance(data, list):
        raw, is_end, next_cursor = data, True, ""
    elif isinstance(data, dict):
        raw: list[Any] = []
        for key in _ENTRY_LIST_KEYS:
            val = data.get(key)
            if isinstance(val, list):
                raw = val
                break
        is_end, next_cursor = _pagination(data)
    else:
        return [], True, ""
    rows: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        folder_id = str(
            item.get("folder_id") or item.get("folderId") or ""
        ).strip()
        media_id = str(
            item.get("media_id") or item.get("mediaId") or ""
        ).strip()
        title = str(
            item.get("title") or item.get("name") or item.get("kb_name") or ""
        ).strip()
        parent = str(
            item.get("parent_folder_id") or item.get("parentFolderId") or ""
        ).strip()
        highlight = str(
            item.get("highlight_content") or item.get("highlightContent") or ""
        )
        is_folder = folder_id.startswith("folder_") or media_id.startswith("folder_")
        if is_folder:
            fid = folder_id or media_id
            if not fid and not title:
                continue
            rows.append(
                {
                    "kind": "folder",
                    "folder_id": fid,
                    "media_id": media_id or fid,
                    "title": title,
                    "parent_folder_id": parent,
                    "highlight_content": highlight,
                    "file_number": item.get("file_number") or item.get("fileNumber") or 0,
                }
            )
            continue
        if not media_id and not title:
            continue
        rows.append(
            {
                "kind": "file",
                "media_id": media_id,
                "title": title,
                "parent_folder_id": parent,
                "highlight_content": highlight,
            }
        )
    return rows, is_end, next_cursor


async def list_visible_knowledge_bases(
    client: ImaClient,
    *,
    query: str = "",
    cursor: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """List wiki libraries. Empty query lists all; falls back to addable + cursor=0."""
    data = await search_knowledge_base(
        client, query=query, cursor=cursor, limit=limit
    )
    rows, is_end, next_cursor, data_keys = extract_knowledge_bases(data)
    blank_query = not (query or "").strip()
    if not rows and blank_query and not (cursor or "").strip():
        data0 = await search_knowledge_base(
            client, query=query, cursor="0", limit=limit
        )
        rows0, end0, cur0, keys0 = extract_knowledge_bases(data0)
        data_keys = list(dict.fromkeys([*data_keys, *keys0]))
        if rows0:
            rows, is_end, next_cursor = rows0, end0, cur0
    if not rows and blank_query:
        try:
            extra = await get_addable_knowledge_base_list(
                client, cursor=cursor or "", limit=limit
            )
        except ImaError:
            extra = {}
        extra_rows, extra_end, extra_cursor, extra_keys = extract_knowledge_bases(extra)
        data_keys = list(dict.fromkeys([*data_keys, *extra_keys]))
        if extra_rows:
            rows, is_end, next_cursor = extra_rows, extra_end, extra_cursor
        elif not (cursor or "").strip():
            try:
                extra0 = await get_addable_knowledge_base_list(
                    client, cursor="0", limit=limit
                )
            except ImaError:
                extra0 = {}
            rows0, end0, cur0, keys0 = extract_knowledge_bases(extra0)
            data_keys = list(dict.fromkeys([*data_keys, *keys0]))
            if rows0:
                rows, is_end, next_cursor = rows0, end0, cur0
    payload: dict[str, Any] = {
        "items": rows,
        "is_end": is_end,
        "next_cursor": next_cursor,
        "data_keys": data_keys,
    }
    if not rows:
        payload["hint"] = EMPTY_KB_HINT
    return payload


async def search_knowledge_base(
    client: ImaClient,
    *,
    query: str = "",
    cursor: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    limit = max(1, min(int(limit or 20), 20))
    data = await client.post(
        "openapi/wiki/v1/search_knowledge_base",
        {"query": query or "", "cursor": cursor or "", "limit": limit},
    )
    return _as_dict(data)


async def get_addable_knowledge_base_list(
    client: ImaClient,
    *,
    cursor: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    limit = max(1, min(int(limit or 20), 50))
    data = await client.post(
        "openapi/wiki/v1/get_addable_knowledge_base_list",
        {"cursor": cursor or "", "limit": limit},
    )
    return _as_dict(data, list_key="addable_knowledge_base_list")


async def get_knowledge_base(client: ImaClient, ids: list[str]) -> dict[str, Any]:
    uniq: list[str] = []
    seen: set[str] = set()
    for raw in ids:
        kid = str(raw or "").strip()
        if not kid or kid in seen:
            continue
        seen.add(kid)
        uniq.append(kid)
        if len(uniq) >= 20:
            break
    if not uniq:
        return {"infos": {}}
    data = await client.post("openapi/wiki/v1/get_knowledge_base", {"ids": uniq})
    return data if isinstance(data, dict) else {}


async def get_knowledge_list(
    client: ImaClient,
    *,
    knowledge_base_id: str,
    cursor: str = "",
    limit: int = 20,
    folder_id: str | None = None,
) -> dict[str, Any]:
    limit = max(1, min(int(limit or 20), 50))
    body: dict[str, Any] = {
        "knowledge_base_id": knowledge_base_id,
        "cursor": cursor or "",
        "limit": limit,
    }
    if folder_id:
        body["folder_id"] = folder_id
    data = await client.post("openapi/wiki/v1/get_knowledge_list", body)
    return _as_dict(data, list_key="knowledge_list")


async def search_knowledge(
    client: ImaClient,
    *,
    query: str,
    knowledge_base_id: str,
    cursor: str = "",
) -> dict[str, Any]:
    data = await client.post(
        "openapi/wiki/v1/search_knowledge",
        {
            "query": query,
            "knowledge_base_id": knowledge_base_id,
            "cursor": cursor or "",
        },
    )
    return _as_dict(data)


async def get_media_info(client: ImaClient, media_id: str) -> dict[str, Any]:
    data = await client.post("openapi/wiki/v1/get_media_info", {"media_id": media_id})
    return data if isinstance(data, dict) else {}
