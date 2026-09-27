"""Read-only view of the same Playwright browser used by agent tools."""

import asyncio
from typing import Any

from fastapi import APIRouter

from app.tools.builtin.browser import _BROWSER

router = APIRouter(prefix="/api/browser")


@router.get("/state")
async def browser_state() -> dict[str, Any]:
    return await asyncio.to_thread(_BROWSER.state)


@router.get("/screenshot")
async def browser_screenshot() -> dict[str, Any]:
    return await asyncio.to_thread(_BROWSER.screenshot_data_url)
