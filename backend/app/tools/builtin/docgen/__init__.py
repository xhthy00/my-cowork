"""Document generation tools package."""

from app.tools.builtin.docgen import docx_gen, pdf_gen, pptx_gen, xlsx_gen
from app.tools.builtin.docgen.schemas import (
    DocxOutline,
    DocxParagraph,
    PptxSlide,
    TemplateId,
    XlsxSheet,
)

__all__ = [
    "DocxOutline",
    "DocxParagraph",
    "PptxSlide",
    "TemplateId",
    "XlsxSheet",
    "docx_gen",
    "pdf_gen",
    "pptx_gen",
    "xlsx_gen",
]
