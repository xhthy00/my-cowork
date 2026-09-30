"""Require the Electron-owned token for executable industry-app APIs."""

from __future__ import annotations

import os
import secrets

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class IndustryAppAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        if path == "/api/industry-apps" or path.startswith("/api/industry-apps/") or path.startswith("/api/apps/"):
            token = os.environ.get("MY_COWORK_INDUSTRY_TOKEN", "")
            provided = request.headers.get("x-mycowork-industry-token", "")
            if not token or not secrets.compare_digest(provided, token):
                return JSONResponse({"detail": "industry app access denied"}, status_code=403)
        return await call_next(request)
