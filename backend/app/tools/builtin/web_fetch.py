"""Fetch a URL and extract readable text (v2 research toolkit)."""

from __future__ import annotations

import re
from html.parser import HTMLParser

import httpx
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

_TIMEOUT = 30.0
_MAX_CHARS = 12_000


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        if tag in {"script", "style", "noscript"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip:
            self._skip -= 1
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = data.strip()
        if text:
            self.parts.append(text)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        return re.sub(r"<[^>]+>", " ", html)
    blob = " ".join(parser.parts)
    blob = re.sub(r"[ \t]+", " ", blob)
    blob = re.sub(r"\n{3,}", "\n\n", blob)
    return blob.strip()


class FetchArgs(BaseModel):
    url: str = Field(description="http(s) URL returned by web_search or provided by the user")


async def web_fetch(url: str) -> str:
    target = (url or "").strip()
    if not target.startswith(("http://", "https://")):
        return "[ERROR] url must start with http:// or https:// — do not invent URLs."
    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "MyCowork/1.0"},
        ) as client:
            res = await client.get(target)
            res.raise_for_status()
            ctype = res.headers.get("content-type", "")
            body = res.text
    except Exception as exc:
        return f"[ERROR] fetch failed: {exc}"
    if "html" in ctype or body.lstrip()[:16].lower().startswith(("<!doctype", "<html")):
        text = html_to_text(body)
    else:
        text = body
    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS] + "\n…(truncated)"
    return f"URL: {target}\n\n{text}"


def make_web_fetch_tool() -> StructuredTool:
    return StructuredTool.from_function(
        coroutine=web_fetch,
        name="web_fetch",
        description=(
            "Fetch a URL and return readable text. Only use URLs from web_search "
            "results or the user. Do not guess URLs."
        ),
        args_schema=FetchArgs,
    )
