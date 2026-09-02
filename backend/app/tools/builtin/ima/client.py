"""HTTP client for the official IMA OpenAPI (POST JSON to ima.qq.com)."""

from __future__ import annotations

from typing import Any

import httpx

from app.tools.builtin.ima.credentials import (
    ImaCredentials,
    MISSING_CREDENTIALS_MSG,
    load_credentials,
)

# Official ima-skills version. Unknown values can make OpenAPI return empty lists.
SKILL_VERSION = "1.1.9"
TIMEOUT = 30.0


def _is_success_code(code: Any) -> bool:
    if code == 0 or code == "0":
        return True
    try:
        return int(code) == 0
    except (TypeError, ValueError):
        return False


class ImaError(Exception):
    """IMA API or credential failure. ``code`` is the business code when known."""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class ImaCredentialError(ImaError):
    """Missing Client ID / API Key."""


class ImaClient:
    def __init__(
        self,
        credentials: ImaCredentials | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._credentials = credentials
        self._transport = transport

    def _creds(self) -> ImaCredentials:
        creds = self._credentials or load_credentials()
        if creds is None or not creds.is_valid():
            raise ImaCredentialError(MISSING_CREDENTIALS_MSG)
        return creds

    def _http_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"timeout": TIMEOUT, "follow_redirects": True}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return kwargs

    def _ima_headers(self, creds: ImaCredentials) -> dict[str, str]:
        return {
            "ima-openapi-clientid": creds.client_id,
            "ima-openapi-apikey": creds.api_key,
            "ima-openapi-ctx": f"skill_version={SKILL_VERSION}",
            "Content-Type": "application/json",
        }

    async def post(self, api_path: str, body: dict[str, Any] | None = None) -> Any:
        creds = self._creds()
        path = api_path.lstrip("/")
        url = f"{creds.base_url}/{path}"
        async with httpx.AsyncClient(**self._http_kwargs()) as http:
            try:
                res = await http.post(url, json=body or {}, headers=self._ima_headers(creds))
            except httpx.HTTPError as exc:
                raise ImaError(f"IMA 请求失败: {exc}") from exc
            except OSError as exc:
                raise ImaError(f"IMA 请求失败: {exc}") from exc
        try:
            payload = res.json()
        except Exception as exc:
            raise ImaError(f"IMA 响应不是 JSON (HTTP {res.status_code})") from exc
        if not isinstance(payload, dict):
            raise ImaError("IMA 响应格式无效")
        code = payload.get("code", payload.get("retcode"))
        if not _is_success_code(code):
            msg = str(payload.get("msg") or payload.get("message") or "IMA API error")
            try:
                code_int = int(code) if code is not None else None
            except (TypeError, ValueError):
                code_int = None
            raise ImaError(msg, code=code_int)
        return payload.get("data") if payload.get("data") is not None else {}

    async def fetch_url(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """GET a media URL. Do not attach IMA API keys — only caller headers."""
        async with httpx.AsyncClient(**self._http_kwargs()) as http:
            try:
                return await http.get(url, headers=headers or {})
            except httpx.HTTPError as exc:
                raise ImaError(f"拉取原文失败: {exc}") from exc
            except OSError as exc:
                raise ImaError(f"拉取原文失败: {exc}") from exc
