"""XLSX generation via openpyxl."""

from __future__ import annotations

from openpyxl import Workbook

from app.sandbox.path_guard import normalize_user_path
from app.tools.builtin.docgen.schemas import XlsxSheet


async def gen(sheet: XlsxSheet | dict, out_path: str) -> str:
    """Write *sheet* to an .xlsx file at *out_path* and return the absolute path."""
    data = sheet if isinstance(sheet, XlsxSheet) else XlsxSheet.model_validate(sheet)
    target = normalize_user_path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = data.sheet_name
    ws.append(list(data.headers))
    for row in data.rows:
        ws.append(list(row))
    wb.save(str(target))
    return str(target)
