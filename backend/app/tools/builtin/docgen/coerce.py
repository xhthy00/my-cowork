"""Coerce messy LLM tool args into docgen schemas.

Models (esp. Anthropic) often stringify nested arrays, rename fields, or wrap
arrays as ``{"item": [...]}`` / ``{"items": [...]}`` due to schema converters.
"""

from __future__ import annotations

import json
from typing import Any

from app.tools.builtin.docgen.schemas import DocxOutline, DocxParagraph, PptxSlide, TemplateId


def _unwrap_item_wrapper(value: Any) -> Any:
    """Unwrap schema-converter artifacts like ``{"item": [...]}``."""
    seen = 0
    while isinstance(value, dict) and seen < 4:
        keys = set(value.keys())
        if keys == {"item"}:
            value = value["item"]
        elif keys == {"items"}:
            value = value["items"]
        else:
            break
        seen += 1
    return value


def _parse_maybe_json(value: Any) -> Any:
    value = _unwrap_item_wrapper(value)
    if not isinstance(value, str):
        return _unwrap_item_wrapper(value)
    text = value.strip()
    if not text:
        return value
    if text[0] not in "[{":
        return value
    try:
        return _unwrap_item_wrapper(json.loads(text))
    except json.JSONDecodeError:
        try:
            return _unwrap_item_wrapper(json.loads(text.replace("'", '"')))
        except json.JSONDecodeError:
            return value


def slides_to_json_string(value: Any) -> str:
    """Normalize any slides payload into a JSON array string for tool args."""
    parsed = _parse_maybe_json(value)
    parsed = _unwrap_item_wrapper(parsed)
    if isinstance(parsed, str):
        return parsed
    if isinstance(parsed, dict) and "slides" in parsed:
        parsed = parsed["slides"]
    return json.dumps(parsed, ensure_ascii=False)


def _as_str_list(value: Any) -> list[str]:
    value = _parse_maybe_json(value)
    if value is None:
        return []
    if isinstance(value, str):
        parts = [p.strip() for p in value.replace("\r", "").split("\n") if p.strip()]
        if len(parts) <= 1 and "；" in value:
            parts = [p.strip() for p in value.split("；") if p.strip()]
        if len(parts) <= 1 and ";" in value and "http" not in value.lower():
            parts = [p.strip() for p in value.split(";") if p.strip()]
        return parts or ([value.strip()] if value.strip() else [])
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            item = _unwrap_item_wrapper(item)
            if item is None:
                continue
            if isinstance(item, dict) and "text" in item:
                s = str(item["text"]).strip()
                if s:
                    out.append(s)
            elif isinstance(item, (list, dict)):
                out.append(json.dumps(item, ensure_ascii=False))
            else:
                s = str(item).strip()
                if s:
                    out.append(s)
        return out
    return [str(value)]


def coerce_pptx_slide(raw: Any) -> PptxSlide:
    raw = _parse_maybe_json(raw)
    if isinstance(raw, PptxSlide):
        return raw
    if isinstance(raw, str):
        return PptxSlide(title=raw.strip() or "幻灯片", bullets=[])
    if not isinstance(raw, dict):
        return PptxSlide(title=str(raw), bullets=[])

    title = (
        raw.get("title")
        or raw.get("heading")
        or raw.get("name")
        or raw.get("slide_title")
        or "幻灯片"
    )
    bullets_raw = (
        raw.get("bullets")
        if "bullets" in raw
        else raw.get("bullet_points")
        if "bullet_points" in raw
        else raw.get("points")
        if "points" in raw
        else raw.get("items")
        if "items" in raw
        else raw.get("content")
        if "content" in raw
        else raw.get("body")
    )
    return PptxSlide(title=str(title).strip() or "幻灯片", bullets=_as_str_list(bullets_raw))


def coerce_pptx_slides(raw: Any) -> list[PptxSlide]:
    raw = _parse_maybe_json(raw)
    if raw is None:
        return []
    if isinstance(raw, dict):
        if any(k in raw for k in ("title", "bullets", "bullet_points", "points")):
            return [coerce_pptx_slide(raw)]
        if "slides" in raw:
            return coerce_pptx_slides(raw["slides"])
    if isinstance(raw, (list, tuple)):
        return [coerce_pptx_slide(item) for item in raw if item is not None]
    if isinstance(raw, str) and raw.strip():
        return [PptxSlide(title=raw.strip(), bullets=[])]
    return []


def coerce_template_id(raw: Any) -> TemplateId:
    text = str(raw or "business").strip().lower()
    if text in {"minimal", "business", "creative"}:
        return text  # type: ignore[return-value]
    if "creat" in text:
        return "creative"
    if "min" in text:
        return "minimal"
    return "business"


def _as_body_text(value: Any) -> str:
    value = _parse_maybe_json(value)
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        parts = [_as_body_text(item) for item in value]
        return "\n\n".join(p for p in parts if p)
    if isinstance(value, dict):
        for key in ("body", "content", "text", "paragraph", "markdown", "paragraphs"):
            if key in value:
                return _as_body_text(value[key])
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _table_to_text(table: Any) -> str:
    table = _parse_maybe_json(table)
    if not isinstance(table, dict):
        return _as_body_text(table)
    lines: list[str] = []
    cap = table.get("caption") or table.get("title")
    if cap:
        lines.append(str(cap).strip())
    headers = table.get("headers") or table.get("columns") or []
    if isinstance(headers, (list, tuple)) and headers:
        lines.append(" | ".join(str(h) for h in headers))
        lines.append(" | ".join("---" for _ in headers))
    for row in table.get("rows") or []:
        if isinstance(row, (list, tuple)):
            lines.append(" | ".join(str(c) for c in row))
        else:
            t = _as_body_text(row)
            if t:
                lines.append(t)
    return "\n".join(lines).strip()


def coerce_docx_paragraph(raw: Any) -> DocxParagraph | None:
    raw = _parse_maybe_json(raw)
    if raw is None:
        return None
    if isinstance(raw, DocxParagraph):
        return raw if (raw.body or "").strip() else None
    if isinstance(raw, str):
        text = raw.strip()
        return DocxParagraph(heading="", body=text) if text else None
    if not isinstance(raw, dict):
        text = str(raw).strip()
        return DocxParagraph(heading="", body=text) if text else None

    # Nested report section handled by _section_to_paragraphs.
    if any(k in raw for k in ("paragraphs", "subsections", "tables", "callout")):
        return None

    heading = (
        raw.get("heading")
        or raw.get("title")
        or raw.get("name")
        or raw.get("section")
        or ""
    )
    body = _as_body_text(
        raw.get("body")
        if "body" in raw
        else raw.get("content")
        if "content" in raw
        else raw.get("text")
        if "text" in raw
        else raw.get("paragraph")
        if "paragraph" in raw
        else raw.get("markdown")
        if "markdown" in raw
        else raw.get("bullets")
        if "bullets" in raw
        else ""
    )
    if isinstance(raw.get("bullets"), (list, tuple)) and not body:
        body = "\n".join(f"- {s}" for s in _as_str_list(raw.get("bullets")))
    body = body.strip()
    if not body:
        return None
    return DocxParagraph(heading=str(heading).strip(), body=body)


def _section_to_paragraphs(section: Any) -> list[DocxParagraph]:
    """Expand LLM section objects into flat heading/body paragraphs."""
    section = _parse_maybe_json(section)
    if section is None:
        return []
    if isinstance(section, str):
        text = section.strip()
        return [DocxParagraph(heading="", body=text)] if text else []
    if not isinstance(section, dict):
        flat = coerce_docx_paragraph(section)
        return [flat] if flat else []

    nested = any(k in section for k in ("paragraphs", "subsections", "tables", "callout"))
    if not nested:
        flat = coerce_docx_paragraph(section)
        return [flat] if flat else []

    heading = str(
        section.get("heading") or section.get("title") or section.get("name") or ""
    ).strip()
    parts: list[str] = []

    if "paragraphs" in section:
        paras = _parse_maybe_json(section.get("paragraphs"))
        if isinstance(paras, (list, tuple)):
            chunk = [t for t in (_as_body_text(p) for p in paras) if t]
            if chunk:
                parts.append("\n\n".join(chunk))
        else:
            t = _as_body_text(paras)
            if t:
                parts.append(t)

    for key in ("body", "content", "text", "callout"):
        if key in section and section.get(key):
            t = _as_body_text(section.get(key))
            if t:
                parts.append(t)

    for table in section.get("tables") or []:
        t = _table_to_text(table)
        if t:
            parts.append(t)

    out: list[DocxParagraph] = []
    body = "\n\n".join(parts).strip()
    if body:
        out.append(DocxParagraph(heading=heading, body=body))

    for sub in section.get("subsections") or []:
        out.extend(_section_to_paragraphs(sub))
    return out


def coerce_docx_outline(raw: Any) -> DocxOutline:
    """Normalize messy LLM docx outline args into DocxOutline."""
    raw = _parse_maybe_json(raw)
    if isinstance(raw, DocxOutline):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        return DocxOutline(
            title="文档",
            paragraphs=[DocxParagraph(heading="", body=text)] if text else [],
        )
    if not isinstance(raw, dict):
        return DocxOutline(title="文档", paragraphs=[])

    title = (
        raw.get("title")
        or raw.get("name")
        or raw.get("doc_title")
        or raw.get("heading")
        or "文档"
    )
    paragraphs: list[DocxParagraph] = []

    # Prefer rich ``sections`` (common LLM shape) over flat paragraphs.
    sections = raw.get("sections") if "sections" in raw else raw.get("chapters")
    if sections is not None:
        sections = _parse_maybe_json(sections)
        if isinstance(sections, (list, tuple)):
            for item in sections:
                paragraphs.extend(_section_to_paragraphs(item))
        elif sections:
            paragraphs.extend(_section_to_paragraphs(sections))

    if not paragraphs and "paragraphs" in raw:
        paras_raw = _parse_maybe_json(raw.get("paragraphs"))
        if isinstance(paras_raw, (list, tuple)):
            for item in paras_raw:
                paragraphs.extend(_section_to_paragraphs(item))
        elif isinstance(paras_raw, str) and paras_raw.strip():
            paragraphs.append(DocxParagraph(heading="", body=paras_raw.strip()))
        elif isinstance(paras_raw, dict):
            paragraphs.extend(_section_to_paragraphs(paras_raw))

    if not paragraphs and "blocks" in raw:
        blocks = _parse_maybe_json(raw.get("blocks"))
        if isinstance(blocks, (list, tuple)):
            for item in blocks:
                paragraphs.extend(_section_to_paragraphs(item))

    if not any((p.body or "").strip() for p in paragraphs):
        fallback = _as_body_text(
            raw.get("body")
            if "body" in raw
            else raw.get("content")
            if "content" in raw
            else raw.get("text")
            if "text" in raw
            else raw.get("markdown")
            if "markdown" in raw
            else ""
        )
        paragraphs = [DocxParagraph(heading="", body=fallback)] if fallback else []

    paragraphs = [p for p in paragraphs if (p.body or "").strip()]
    return DocxOutline(title=str(title).strip() or "文档", paragraphs=paragraphs)


def docx_outline_has_body(outline: DocxOutline) -> bool:
    return any((p.body or "").strip() for p in outline.paragraphs)
