"""Authenticate host APIs before any route, including streams and confirmations."""

from __future__ import annotations

import os
import secrets

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class IndustryAppAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, protect_all: bool = True):
        super().__init__(app)
        self.protect_all = protect_all

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        industry = path == "/api/industry-apps" or path.startswith("/api/industry-apps/") or path.startswith("/api/apps/")
        if industry or (self.protect_all and path.startswith("/api/")):
            token = os.environ.get("MY_COWORK_INDUSTRY_TOKEN", "")
            provided = request.headers.get("x-mycowork-industry-token", "")
            if not token or not secrets.compare_digest(provided, token) or request.headers.get("origin"):
                return JSONResponse({"detail": "host API access denied"}, status_code=403)
        return await call_next(request)
