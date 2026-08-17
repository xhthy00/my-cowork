"""PDF generation via Electron printToPDF HTTP bridge."""

from __future__ import annotations

import os

import httpx

from app.sandbox.path_guard import normalize_user_path


async def gen(html: str, out_path: str, *, pdf_port: int | None = None) -> str:
    """Render *html* to PDF through Electron and write bytes to *out_path*."""
    port = pdf_port or int(os.environ.get("ELECTRON_PDF_PORT", "0") or "0")
    if not port:
        raise RuntimeError(
            "ELECTRON_PDF_PORT is not set; Electron PDF bridge is unavailable."
        )

    target = normalize_user_path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"http://127.0.0.1:{port}/print-to-pdf",
            json={"html": html},
        )
        resp.raise_for_status()
        target.write_bytes(resp.content)

    return str(target)
