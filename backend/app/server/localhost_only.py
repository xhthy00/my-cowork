"""Reject non-local requests except /webhook/* (tunnel exposure surface).

Middleware responsibilities:
  * Block any non-loopback client on non-``/webhook`` paths.
  * Pass ``/webhook/*`` through unchanged; downstream ``webhook_lark`` route
    is responsible for IP allowlist + signature verification (see
    ``LARK_IPS`` env var and ``verify_lark_signature``).

Cloudflared forwards traffic to the bound loopback socket, so once it
reaches this middleware every request looks like ``127.0.0.1`` — the
allowlist inside webhook_lark is the real barrier for tunnel-exposed paths.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


def _client_host(request: Request) -> str:
    if request.client is None:
        return ""
    return request.client.host or ""


def _is_loopback(host: str) -> bool:
    return host in {"127.0.0.1", "::1", "localhost", "testclient"}


class LocalhostOnlyMiddleware(BaseHTTPMiddleware):
    """Allow only loopback clients, except paths under ``/webhook``."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        if path == "/webhook" or path.startswith("/webhook/"):
            return await call_next(request)
        host = _client_host(request)
        if not _is_loopback(host):
            return JSONResponse({"detail": "forbidden"}, status_code=403)
        return await call_next(request)
