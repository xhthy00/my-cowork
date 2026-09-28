"""Office generation command policy shared by execution paths."""

import re

_PANDOC_REFUSE = (
    "[ERROR] Do not use pandoc/LibreOffice to create Word/PPT/Excel. "
    "Load officecli-docx (or officecli-pptx / officecli-xlsx) and write the "
    "file with officecli via bash. Fallback: docx_gen / pptx_gen / xlsx_gen "
    "only if officecli is missing. Do not convert HTML/Markdown into .docx."
)
_PANDOC_TO_OFFICE_RE = re.compile(
    r"\bpandoc\b",
    re.IGNORECASE,
)
_PANDOC_OFFICE_EXT_RE = re.compile(
    r"\.(?:docx?|pptx?|xlsx)\b|-t\s+docx|--to=docx",
    re.IGNORECASE,
)
_LIBRE_CONVERT_RE = re.compile(
    r"\b(?:soffice|libreoffice)\b[\s\S]{0,200}?--convert-to\s+(?:docx?|pptx?|xlsx)\b",
    re.IGNORECASE,
)


def office_bypass_refuse(cmd: str) -> str | None:
    """Refuse HTML/md→Office converters; Word/PPT/Excel must use officecli."""
    q = (cmd or "").strip()
    if not q:
        return None
    if _PANDOC_TO_OFFICE_RE.search(q) and _PANDOC_OFFICE_EXT_RE.search(q):
        return _PANDOC_REFUSE
    if _LIBRE_CONVERT_RE.search(q):
        return _PANDOC_REFUSE
    return None
