"""Unit tests for pdf_gen (Electron bridge mocked with respx)."""

from pathlib import Path

import httpx
import pytest
import respx

from app.tools.builtin.docgen.pdf_gen import gen


@pytest.mark.asyncio
@respx.mock
async def test_pdf_gen_writes_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ELECTRON_PDF_PORT", "19222")
    out = tmp_path / "doc.pdf"
    pdf_bytes = b"%PDF-1.4 fake"

    route = respx.post("http://127.0.0.1:19222/print-to-pdf").mock(
        return_value=httpx.Response(200, content=pdf_bytes)
    )
    path = await gen("<h1>Hi</h1>", str(out))
    assert route.called
    assert Path(path).read_bytes() == pdf_bytes


@pytest.mark.asyncio
async def test_pdf_gen_requires_port(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ELECTRON_PDF_PORT", raising=False)
    with pytest.raises(RuntimeError, match="ELECTRON_PDF_PORT"):
        await gen("<h1>x</h1>", str(tmp_path / "a.pdf"))
