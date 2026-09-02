"""IMA notes OpenAPI — only get_doc_content for wiki notebook media."""

from __future__ import annotations

from typing import Any

from app.tools.builtin.ima.client import ImaClient


async def get_doc_content(client: ImaClient, note_id: str) -> dict[str, Any]:
    data = await client.post(
        "openapi/note/v1/get_doc_content",
        {"note_id": note_id, "target_content_format": 0},
    )
    return data if isinstance(data, dict) else {}
