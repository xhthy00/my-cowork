"""SkillHub.cn public catalog + zip download (WorkBuddy-style marketplace)."""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

DEFAULT_BASE = "https://api.skillhub.cn"
MAX_ZIP_BYTES = 50 * 1024 * 1024
TIMEOUT_SECONDS = 60.0
_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_COS_SUFFIXES = (".myqcloud.com", ".qcloud.com")


class SkillHubError(Exception):
    """Upstream or validation failure talking to SkillHub."""

    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


def api_base() -> str:
    raw = (os.environ.get("SKILLHUB_API_BASE") or DEFAULT_BASE).strip().rstrip("/")
    if not raw:
        raw = DEFAULT_BASE
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SkillHubError("invalid SkillHub API base", status_code=400)
    return raw


def validate_id(value: str, *, field: str) -> str:
    text = (value or "").strip()
    if not text or not _ID_RE.match(text) or len(text) > 128:
        raise SkillHubError(f"invalid {field}", status_code=400)
    return text


def _allowed_hosts(base: str) -> set[str]:
    host = urlparse(base).netloc.lower().split("@")[-1].split(":")[0]
    return {host} if host else set()


def assert_allowed_url(url: str, *, base: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise SkillHubError("blocked redirect host", status_code=400)
    host = (parsed.hostname or "").lower()
    if not host:
        raise SkillHubError("blocked redirect host", status_code=400)
    allowed = _allowed_hosts(base)
    if host in allowed:
        return
    if parsed.scheme == "https" and any(host.endswith(suf) for suf in _COS_SUFFIXES):
        return
    raise SkillHubError("blocked redirect host", status_code=400)


def _labels_requires_api_key(labels: Any) -> bool:
    if not isinstance(labels, dict):
        return False
    raw = labels.get("requires_api_key")
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() in {"1", "true", "yes"}


def normalize_skill(raw: dict[str, Any]) -> dict[str, Any] | None:
    slug = str(raw.get("slug") or "").strip()
    if not slug:
        return None
    ns = raw.get("namespace") if isinstance(raw.get("namespace"), dict) else {}
    handle = str(ns.get("handle") or raw.get("ownerName") or "").strip()
    desc = str(raw.get("description_zh") or raw.get("description") or "").strip()
    return {
        "name": str(raw.get("name") or slug),
        "description": desc,
        "iconUrl": raw.get("iconUrl") or None,
        "downloads": int(raw.get("downloads") or 0),
        "stars": int(raw.get("stars") or 0),
        "category": str(raw.get("category") or ""),
        "slug": slug,
        "handle": handle,
        "version": str(raw.get("version") or ""),
        "requiresApiKey": _labels_requires_api_key(raw.get("labels")),
        "homepage": str(raw.get("homepage") or ""),
    }


def _download_urls(base: str, handle: str, slug: str) -> list[str]:
    return [
        f"{base}/api/v1/download?slug={slug}&namespace={handle}",
        f"{base}/api/v1/download?slug={slug}",
        f"{base}/api/v1/skills/{handle}/{slug}/download",
        f"{base}/api/skills/{handle}/{slug}/download",
    ]


async def _read_limited(resp: httpx.Response) -> bytes:
    length = resp.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_ZIP_BYTES:
        raise SkillHubError("package too large", status_code=400)
    buf = bytearray()
    async for chunk in resp.aiter_bytes():
        buf.extend(chunk)
        if len(buf) > MAX_ZIP_BYTES:
            raise SkillHubError("package too large", status_code=400)
    return bytes(buf)


async def _fetch_bytes(client: httpx.AsyncClient, url: str, *, base: str) -> httpx.Response:
    current = url
    for _ in range(5):
        assert_allowed_url(current, base=base)
        async with client.stream("GET", current, follow_redirects=False) as resp:
            if resp.status_code in {301, 302, 303, 307, 308}:
                loc = resp.headers.get("location")
                if not loc:
                    raise SkillHubError("redirect missing location")
                current = urljoin(current, loc)
                continue
            body = await _read_limited(resp)
            return httpx.Response(
                status_code=resp.status_code,
                headers=resp.headers,
                content=body,
            )
    raise SkillHubError("too many redirects")


async def list_hub_skills(
    *,
    keyword: str = "",
    category: str = "",
    sort_by: str = "score",
    page: int = 1,
    page_size: int = 12,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    base = api_base()
    params: dict[str, str | int] = {
        "page": max(1, page),
        "pageSize": max(1, min(page_size, 50)),
        "sortBy": sort_by or "score",
    }
    if keyword.strip():
        params["keyword"] = keyword.strip()
    if category.strip():
        params["category"] = category.strip()

    async def _get(http: httpx.AsyncClient) -> dict[str, Any]:
        try:
            resp = await http.get(f"{base}/api/skills", params=params)
        except httpx.HTTPError as exc:
            raise SkillHubError(f"SkillHub unreachable: {exc}") from exc
        if resp.status_code >= 500:
            raise SkillHubError(f"SkillHub list failed: {resp.status_code}")
        if resp.status_code >= 400:
            raise SkillHubError(f"SkillHub list failed: {resp.status_code}", status_code=400)
        try:
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise SkillHubError("SkillHub returned invalid JSON") from exc
        if not isinstance(payload, dict) or payload.get("code") not in (0, None):
            raise SkillHubError(str(payload.get("message") or "SkillHub list failed"))
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        raw_skills = data.get("skills") if isinstance(data, dict) else None
        if not isinstance(raw_skills, list):
            raise SkillHubError("SkillHub list missing skills")
        skills = [item for item in (normalize_skill(s) for s in raw_skills if isinstance(s, dict)) if item]
        total = int(data.get("total") or len(skills)) if isinstance(data, dict) else len(skills)
        return {"skills": skills, "total": total}

    if client is not None:
        return await _get(client)
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as http:
        return await _get(http)


async def download_hub_skill(
    handle: str,
    slug: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> bytes:
    handle = validate_id(handle, field="handle")
    slug = validate_id(slug, field="slug")
    base = api_base()
    urls = _download_urls(base, handle, slug)
    last_error: SkillHubError | None = None

    async def _try(http: httpx.AsyncClient) -> bytes:
        nonlocal last_error
        for url in urls:
            try:
                resp = await _fetch_bytes(http, url, base=base)
            except SkillHubError as exc:
                last_error = exc
                if exc.status_code == 400 and "blocked" in str(exc):
                    raise
                if exc.status_code == 400 and "too large" in str(exc):
                    raise
                continue
            except httpx.HTTPError as exc:
                last_error = SkillHubError(f"SkillHub unreachable: {exc}")
                continue
            if resp.status_code in {404, 405}:
                last_error = SkillHubError(f"SkillHub download failed: {resp.status_code}")
                continue
            if resp.status_code >= 500:
                raise SkillHubError(f"SkillHub download failed: {resp.status_code}")
            if resp.status_code >= 400:
                raise SkillHubError(
                    f"SkillHub download failed: {resp.status_code}",
                    status_code=400,
                )
            body = resp.content
            if not body.startswith(b"PK"):
                last_error = SkillHubError("SkillHub download was not a zip")
                continue
            return body
        raise last_error or SkillHubError("SkillHub download failed")

    if client is not None:
        return await _try(client)
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as http:
        return await _try(http)
