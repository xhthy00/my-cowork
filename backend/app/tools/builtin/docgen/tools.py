"""LangChain tool wrappers for document generators."""

from __future__ import annotations

import json
import uuid
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, field_validator, model_validator

from app.guardrails.approval import ConfirmHub
from app.sandbox.path_guard import PathGuard, PathGuardError, resolve_write_path
from app.tools.builtin.docgen import docx_gen, pdf_gen, pptx_gen, xlsx_gen
from app.tools.builtin.docgen.gongwen_format import apply_body_manuscript_format
from app.tools.builtin.docgen.coerce import (
    coerce_docx_outline,
    coerce_pptx_slides,
    coerce_template_id,
    docx_outline_has_body,
    slides_to_json_string,
)
from app.tools.builtin.docgen.schemas import DocxOutline, TemplateId, XlsxSheet


class DocxArgs(BaseModel):
    outline: dict[str, Any]
    out_path: str

    @field_validator("outline", mode="before")
    @classmethod
    def _coerce_outline(cls, v: Any) -> dict[str, Any]:
        data = coerce_docx_outline(v)
        return data.model_dump()

    @model_validator(mode="after")
    def _require_body(self) -> DocxArgs:
        data = DocxOutline.model_validate(self.outline)
        if not docx_outline_has_body(data):
            raise ValueError(
                "outline.paragraphs must include non-empty body text "
                '(e.g. {"title":"报告","paragraphs":[{"heading":"概述","body":"……"}]})'
            )
        return self


class PptxArgs(BaseModel):
    """Flat string schema — avoids nested-array JSON Schema bugs with Anthropic.

    Nested ``list[dict]`` / ``list[str]`` schemas are frequently rewritten by
    converters into ``{"item": [...]}``, which then fails validation. Both
    ``slides_json`` and legacy ``slides`` are advertised as *strings* only;
    lists/dicts are coerced to JSON strings before validation.
    """

    template_id: TemplateId = Field(
        default="business",
        description="One of: minimal | business | creative",
    )
    slides_json: str | None = Field(
        default=None,
        description=(
            "Preferred: JSON string of slides, e.g. "
            '\'[{"title":"封面","bullets":["副标题"]},{"title":"行程","bullets":["D1","D2"]}]\''
        ),
    )
    slides: str | None = Field(
        default=None,
        description=(
            "Alias for slides_json. Must be a JSON string of the slides array "
            "(not a nested array/object field)."
        ),
    )
    out_path: str = Field(
        ...,
  description="Output path under the task working directory (absolute). Desktop is remapped when a workspace task is active.",
)

    @field_validator("template_id", mode="before")
    @classmethod
    def _template(cls, v: Any) -> TemplateId:
        return coerce_template_id(v)

    @field_validator("slides_json", "slides", mode="before")
    @classmethod
    def _stringify_slides(cls, v: Any) -> str | None:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            return v
        # list/dict / {"item":[...]} → JSON string (keeps schema type=string)
        return slides_to_json_string(v)

    @model_validator(mode="after")
    def _normalize(self) -> PptxArgs:
        raw = self.slides_json or self.slides
        if not raw:
            raise ValueError(
                "slides_json (or slides) is required as a JSON string like "
                '\'[{"title":"封面","bullets":["要点1"]}]\''
            )
        parsed = coerce_pptx_slides(raw)
        if not parsed:
            raise ValueError(
                "slides_json must decode to a non-empty slides array"
            )
        normalized = json.dumps(
            [{"title": s.title, "bullets": s.bullets} for s in parsed],
            ensure_ascii=False,
        )
        self.slides_json = normalized
        self.slides = None
        return self

    def parsed_slides(self) -> list[dict[str, Any]]:
        return json.loads(self.slides_json or "[]")


class XlsxArgs(BaseModel):
    sheet: dict[str, Any]
    out_path: str


class PdfArgs(BaseModel):
    html: str
    out_path: str


async def _confirm(
    hub: ConfirmHub | None,
    tool: str,
    args: dict[str, Any],
) -> bool:
    if hub is None:
        return True
    call_id = f"{tool}:{uuid.uuid4().hex}"
    return await hub.request(call_id, tool, args)


def _guarded_out_path(guard: PathGuard, out_path: str) -> str:
    """Return resolved write path, or an ``[ERROR] …`` string on failure."""
    from app.runtime.v2.office_gate import OFFICE_WRITE_REFUSE, office_writes_blocked

    if office_writes_blocked():
        return OFFICE_WRITE_REFUSE
    try:
        target = str(resolve_write_path(out_path))
        guard.check_path(target)
        return target
    except PathGuardError as exc:
        return f"[ERROR] {exc}"
    except Exception as exc:
        return f"[ERROR] Invalid path: {exc}"


def make_docx_tool(guard: PathGuard, hub: ConfirmHub | None) -> StructuredTool:
    async def _run(outline: dict[str, Any], out_path: str) -> str:
        try:
            args = DocxArgs.model_validate({"outline": outline, "out_path": out_path})
        except Exception as exc:
            return (
                "docx_gen 参数无效：outline 需要 title + 非空正文。"
                '示例：outline={"title":"报告","paragraphs":[{"heading":"概述","body":"分析结论……"}]} '
                f"错误详情: {exc}"
            )
        target = _guarded_out_path(guard, args.out_path)
        if target.startswith("[ERROR]"):
            return target
        ok = await _confirm(
            hub, "docx.gen", {"out_path": target, "outline": args.outline}
        )
        if not ok:
            return "Operation rejected by user"
        try:
            return await docx_gen.gen(args.outline, target)
        except Exception as exc:
            return f"docx_gen 生成失败: {exc}"

    return StructuredTool.from_function(
        coroutine=_run,
        name="docx_gen",
        description=(
            "Generate a DOCX from an outline and write it to out_path. "
            "outline MUST include title and paragraphs with non-empty body text, e.g. "
            '{"title":"报告","paragraphs":[{"heading":"概述","body":"……正文……"}]}. '
            "Do not call with title-only outline."
        ),
        args_schema=DocxArgs,
    )


def make_pptx_tool(guard: PathGuard, hub: ConfirmHub | None) -> StructuredTool:
    async def _run(
        out_path: str = "",
        template_id: TemplateId = "business",
        slides_json: str | None = None,
        slides: str | None = None,
    ) -> str:
        try:
            args = PptxArgs.model_validate(
                {
                    "template_id": template_id,
                    "out_path": out_path,
                    "slides_json": slides_json,
                    "slides": slides,
                }
            )
        except Exception as exc:
            return (
                "pptx_gen 参数无效。请把 slides_json 作为 JSON 字符串传入，例如："
                'slides_json=\'[{"title":"封面","bullets":["副标题"]},'
                '{"title":"行程","bullets":["D1","D2"]}]\' '
                f"错误详情: {exc}"
            )
        target = _guarded_out_path(guard, args.out_path)
        if target.startswith("[ERROR]"):
            return target
        slide_list = args.parsed_slides()
        ok = await _confirm(
            hub,
            "pptx.gen",
            {
                "out_path": target,
                "template_id": args.template_id,
                "slides": slide_list,
            },
        )
        if not ok:
            return "Operation rejected by user"
        try:
            return await pptx_gen.gen(args.template_id, slide_list, target)
        except Exception as exc:
            return f"pptx_gen 生成失败: {exc}"

    return StructuredTool.from_function(
        coroutine=_run,
        name="pptx_gen",
        description=(
            "Generate a PPTX file. Pass slides_json as a JSON STRING "
            '(e.g. \'[{"title":"封面","bullets":["要点"]}]\'), '
            "template_id (minimal|business|creative), and out_path "
            "(absolute path under the task working directory). Do NOT use pdf_gen for PPT requests. "
            "Do NOT wrap arrays as {\"item\": [...]}."
        ),
        args_schema=PptxArgs,
    )


def make_xlsx_tool(guard: PathGuard, hub: ConfirmHub | None) -> StructuredTool:
    async def _run(sheet: dict[str, Any], out_path: str) -> str:
        target = _guarded_out_path(guard, out_path)
        if target.startswith("[ERROR]"):
            return target
        ok = await _confirm(hub, "xlsx.gen", {"out_path": target, "sheet": sheet})
        if not ok:
            return "Operation rejected by user"
        return await xlsx_gen.gen(XlsxSheet.model_validate(sheet), target)

    return StructuredTool.from_function(
        coroutine=_run,
        name="xlsx_gen",
        description="Generate an XLSX from headers/rows JSON and write it to out_path.",
        args_schema=XlsxArgs,
    )


class GongwenFormatArgs(BaseModel):
    path: str = Field(..., description="Absolute path to an existing .docx to restyle.")


def make_gongwen_format_tool(guard: PathGuard, hub: ConfirmHub | None) -> StructuredTool:
    async def _run(path: str) -> str:
        target = _guarded_out_path(guard, path)
        if target.startswith("[ERROR]"):
            return target
        if not target.lower().endswith(".docx"):
            return "[ERROR] docx_gongwen_format 只接受 .docx 文件"
        from pathlib import Path as _Path

        if not _Path(target).is_file():
            return f"[ERROR] 文件不存在: {target}"
        try:
            return apply_body_manuscript_format(target)
        except Exception as exc:
            return f"docx_gongwen_format 失败: {exc}"

    return StructuredTool.from_function(
        coroutine=_run,
        name="docx_gongwen_format",
        description=(
            "Apply 公文正文稿 format to an existing .docx: margins 3cm/2.9cm, "
            "exact 29pt line spacing, 方正 GBK fonts, Times New Roman digits, "
            "and a centered long-dash page number. Call this after writing a "
            "Party/government official document. Do not use GB/T 9704 "
            "3.7cm/2.8cm/28pt/仿宋_GB2312 page setup."
        ),
        args_schema=GongwenFormatArgs,
    )


def make_pdf_tool(guard: PathGuard, hub: ConfirmHub | None) -> StructuredTool:
    async def _run(html: str, out_path: str) -> str:
        target = _guarded_out_path(guard, out_path)
        if target.startswith("[ERROR]"):
            return target
        ok = await _confirm(hub, "pdf.gen", {"out_path": target, "html": html[:200]})
        if not ok:
            return "Operation rejected by user"
        return await pdf_gen.gen(html, target)

    return StructuredTool.from_function(
        coroutine=_run,
        name="pdf_gen",
        description="Render HTML to PDF via Electron printToPDF and write to out_path.",
        args_schema=PdfArgs,
    )
