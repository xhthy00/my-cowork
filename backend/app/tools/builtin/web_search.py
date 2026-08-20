"""Built-in web search — AionUi-style provider registry with a no-key fallback."""

from __future__ import annotations

import os
import time
from typing import Any
from urllib.parse import quote_plus

import httpx
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_CACHE_TTL = 15 * 60
_TIMEOUT = 30.0


class SearchArgs(BaseModel):
    query: str = Field(description="Search query")
    count: int = Field(default=5, description="Max results (1-10)")


def _cache_get(key: str) -> list[dict[str, Any]] | None:
    hit = _CACHE.get(key)
    if not hit:
        return None
    ts, rows = hit
    if time.time() - ts > _CACHE_TTL:
        _CACHE.pop(key, None)
        return None
    return rows


def _cache_set(key: str, rows: list[dict[str, Any]]) -> None:
    _CACHE[key] = (time.time(), rows)


def _normalize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        url = str(row.get("url") or "").strip()
        title = str(row.get("title") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(
            {
                "title": title or url,
                "url": url,
                "snippet": str(row.get("snippet") or row.get("description") or ""),
                "published": str(row.get("published") or row.get("date") or ""),
            }
        )
    return out


def _env(name: str, *alts: str) -> str:
    for key in (name, *alts):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    web = _toml_web()
    mapping = {
        "BRAVE_API_KEY": "brave_key",
        "MY_COWORK_BRAVE_KEY": "brave_key",
        "TAVILY_API_KEY": "tavily_key",
        "MY_COWORK_TAVILY_KEY": "tavily_key",
        "BOCHA_API_KEY": "bocha_key",
        "MY_COWORK_BOCHA_KEY": "bocha_key",
        "EXA_API_KEY": "exa_key",
        "MY_COWORK_EXA_KEY": "exa_key",
        "SEARXNG_URL": "searxng_url",
        "MY_COWORK_SEARXNG_URL": "searxng_url",
        "MY_COWORK_SEARCH_PROVIDER": "backend",
    }
    for key in (name, *alts):
        field = mapping.get(key)
        if field and str(web.get(field) or "").strip():
            return str(web[field]).strip()
    return ""


def _toml_web() -> dict[str, Any]:
    import tomllib
    from pathlib import Path

    candidates = [
        Path(os.environ.get("MY_COWORK_CONFIG") or ""),
        Path.home() / ".my-cowork" / "config.toml",
        Path(__file__).resolve().parents[4] / "config.toml",
    ]
    for path in candidates:
        if not path or not path.is_file():
            continue
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        web = ((data.get("tools") or {}).get("web") or {})
        if isinstance(web, dict):
            return web
    return {}


async def _brave(query: str, count: int) -> list[dict[str, Any]]:
    key = _env("BRAVE_API_KEY", "MY_COWORK_BRAVE_KEY")
    if not key:
        raise RuntimeError("no key")
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        res = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": count},
            headers={"Accept": "application/json", "X-Subscription-Token": key},
        )
        res.raise_for_status()
        data = res.json()
    web = (data.get("web") or {}).get("results") or []
    return [{"title": r.get("title"), "url": r.get("url"), "snippet": r.get("description")} for r in web]


async def _tavily(query: str, count: int) -> list[dict[str, Any]]:
    key = _env("TAVILY_API_KEY", "MY_COWORK_TAVILY_KEY")
    if not key:
        raise RuntimeError("no key")
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        res = await client.post(
            "https://api.tavily.com/search",
            json={"api_key": key, "query": query, "max_results": count},
        )
        res.raise_for_status()
        data = res.json()
    return [
        {"title": r.get("title"), "url": r.get("url"), "snippet": r.get("content")}
        for r in (data.get("results") or [])
    ]


_BOCHA_URLS = (
    "https://api.bochaai.com/v1/web-search",
    "https://api.bocha.cn/v1/web-search",
)


def _bocha_ok_code(code: Any) -> bool:
    return code in (None, "", 200, "200", 0, "0")


def parse_bocha_payload(payload: Any) -> list[dict[str, Any]]:
    """Accept both ``{data:{webPages:{value}}}`` and top-level ``webPages``."""
    if not isinstance(payload, dict):
        raise RuntimeError("bocha: response is not an object")
    code = payload.get("code")
    if not _bocha_ok_code(code):
        msg = payload.get("msg") or payload.get("message") or payload.get("msgShow") or ""
        raise RuntimeError(f"code={code} {msg}".strip())
    blob = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(blob, dict):
        blob = payload
    web = blob.get("webPages") or blob.get("web_pages") or payload.get("webPages")
    rows: Any
    if isinstance(web, list):
        rows = web
    elif isinstance(web, dict):
        rows = web.get("value") or web.get("results") or web.get("items") or []
    else:
        rows = blob.get("results") or payload.get("results") or []
    if not isinstance(rows, list):
        raise RuntimeError("bocha: webPages.value is not a list")
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "title": row.get("name") or row.get("title"),
                "url": row.get("url") or row.get("displayUrl"),
                "snippet": row.get("snippet") or row.get("summary") or row.get("description"),
                "published": row.get("datePublished") or row.get("dateLastCrawled") or "",
            }
        )
    return out


async def _bocha(query: str, count: int) -> list[dict[str, Any]]:
    key = _env("BOCHA_API_KEY", "MY_COWORK_BOCHA_KEY")
    if not key:
        raise RuntimeError("no key")
    body = {"query": query, "count": count, "summary": True, "freshness": "noLimit"}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    errors: list[str] = []
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for url in _BOCHA_URLS:
            try:
                res = await client.post(url, headers=headers, json=body)
                if res.status_code >= 400:
                    errors.append(f"{url}: HTTP {res.status_code} {res.text[:180]}")
                    continue
                pages = parse_bocha_payload(res.json())
            except Exception as exc:
                errors.append(f"{url}: {exc}")
                continue
            if pages:
                return pages
            errors.append(f"{url}: empty")
    raise RuntimeError("; ".join(errors) or "empty")


async def _exa(query: str, count: int) -> list[dict[str, Any]]:
    key = _env("EXA_API_KEY", "MY_COWORK_EXA_KEY")
    if not key:
        raise RuntimeError("no key")
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        res = await client.post(
            "https://api.exa.ai/search",
            headers={"x-api-key": key, "Content-Type": "application/json"},
            json={"query": query, "numResults": count, "type": "auto"},
        )
        res.raise_for_status()
        data = res.json()
    return [
        {
            "title": r.get("title"),
            "url": r.get("url"),
            "snippet": r.get("text") or r.get("snippet") or "",
            "published": r.get("publishedDate") or "",
        }
        for r in (data.get("results") or [])
    ]


async def _searxng(query: str, count: int) -> list[dict[str, Any]]:
    base = _env("SEARXNG_URL", "MY_COWORK_SEARXNG_URL").rstrip("/")
    if not base:
        raise RuntimeError("no url")
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        res = await client.get(
            f"{base}/search",
            params={"q": query, "format": "json", "language": "zh-CN"},
        )
        res.raise_for_status()
        data = res.json()
    return [
        {"title": r.get("title"), "url": r.get("url"), "snippet": r.get("content")}
        for r in (data.get("results") or [])[:count]
    ]


async def _ddgs(query: str, count: int) -> list[dict[str, Any]]:
    """Zero-config fallback (AionUi-style). Prefer the ddgs package, else HTML."""
    try:
        from ddgs import DDGS  # type: ignore

        rows = DDGS().text(query, max_results=count)
        return [
            {"title": r.get("title"), "url": r.get("href") or r.get("url"), "snippet": r.get("body")}
            for r in rows
        ]
    except Exception:
        pass
    url = "https://html.duckduckgo.com/html/?q=" + quote_plus(query)
    async with httpx.AsyncClient(
        timeout=_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": "MyCowork/1.0"},
    ) as client:
        res = await client.get(url)
        res.raise_for_status()
        html = res.text
    import re

    found: list[dict[str, Any]] = []
    for m in re.finditer(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        html,
        re.I | re.S,
    ):
        href, title = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
        if href.startswith("http"):
            found.append({"title": title.strip(), "url": href, "snippet": ""})
        if len(found) >= count:
            break
    if not found:
        raise RuntimeError("ddgs empty")
    return found


_PROVIDERS = (
    ("bocha", _bocha),
    ("brave", _brave),
    ("tavily", _tavily),
    ("exa", _exa),
    ("searxng", _searxng),
    ("ddgs", _ddgs),
)


def configured_providers() -> list[str]:
    names: list[str] = []
    if _env("BOCHA_API_KEY", "MY_COWORK_BOCHA_KEY"):
        names.append("bocha")
    if _env("BRAVE_API_KEY", "MY_COWORK_BRAVE_KEY"):
        names.append("brave")
    if _env("TAVILY_API_KEY", "MY_COWORK_TAVILY_KEY"):
        names.append("tavily")
    if _env("EXA_API_KEY", "MY_COWORK_EXA_KEY"):
        names.append("exa")
    if _env("SEARXNG_URL", "MY_COWORK_SEARXNG_URL"):
        names.append("searxng")
    preferred = _env("MY_COWORK_SEARCH_PROVIDER").strip().lower()
    if preferred in dict(_PROVIDERS):
        if preferred in names:
            names.remove(preferred)
        names.insert(0, preferred)
    names.append("ddgs")
    # de-dupe preserve order
    out: list[str] = []
    for n in names:
        if n not in out:
            out.append(n)
    return out


async def web_search(query: str, count: int = 5) -> str:
    q = (query or "").strip()
    if not q:
        return "[ERROR] empty query"
    count = max(1, min(int(count or 5), 10))
    cache_key = f"{q}|{count}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return json_dumps(cached)

    errors: list[str] = []
    by_name = dict(_PROVIDERS)
    for name in configured_providers():
        fn = by_name.get(name)
        if fn is None:
            continue
        try:
            rows = _normalize(await fn(q, count))
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            continue
        if rows:
            _cache_set(cache_key, rows)
            return json_dumps(rows)
        errors.append(f"{name}: empty")
    return (
        "[ERROR] No search provider returned results. "
        "Do not invent URLs. Errors: " + "; ".join(errors[:6])
    )


def json_dumps(rows: list[dict[str, Any]]) -> str:
    import json

    return json.dumps(rows, ensure_ascii=False, indent=2)


def make_web_search_tool() -> StructuredTool:
    return StructuredTool.from_function(
        coroutine=web_search,
        name="web_search",
        description=(
            "Search the public web. Returns JSON [{title,url,snippet,published}]. "
            "Must be used for current events, policy, prices, travel, or comparisons. "
            "Never invent URLs — only cite results from this tool."
        ),
        args_schema=SearchArgs,
    )
