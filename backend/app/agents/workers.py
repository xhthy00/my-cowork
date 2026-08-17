"""Canonical workforce worker ids (Eigent-aligned names)."""

from __future__ import annotations

WORKER_IDS = (
    "developer_agent",
    "browser_agent",
    "document_agent",
    "multi_modal_agent",
)

WORKER_LABELS = {
    "developer_agent": "Developer Agent",
    "browser_agent": "Browser Agent",
    "document_agent": "Document Agent",
    "multi_modal_agent": "Multi Modal Agent",
}

# Legacy aliases kept for skills config / old transcripts.
LEGACY_WORKER_MAP = {
    "file_worker": "developer_agent",
    "web_worker": "browser_agent",
    "doc_worker": "document_agent",
    "msg_worker": "multi_modal_agent",
}


def normalize_worker_id(name: str) -> str | None:
    raw = (name or "").strip()
    if raw in WORKER_IDS:
        return raw
    return LEGACY_WORKER_MAP.get(raw)
