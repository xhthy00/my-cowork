"""Pydantic schemas for document generation tools."""

from typing import Literal

from pydantic import BaseModel, Field


class DocxParagraph(BaseModel):
    heading: str
    body: str


class DocxOutline(BaseModel):
    title: str
    paragraphs: list[DocxParagraph] = Field(default_factory=list)


class PptxSlide(BaseModel):
    title: str
    bullets: list[str] = Field(default_factory=list)


TemplateId = Literal["minimal", "business", "creative"]


class XlsxSheet(BaseModel):
    headers: list[str]
    rows: list[list] = Field(default_factory=list)
    sheet_name: str = "Sheet1"
