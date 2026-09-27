# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Windows one-dir backend.

Outputs ``dist/python_runtime/python.exe`` plus sibling DLLs/packages.
One-dir avoids the per-launch temp extraction of one-file (10-30s on Windows),
so cold start drops to ~1-3s. ``python_runner.ts`` already prefers this path:
``resources/python_runtime/python.exe``.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_all

block_cipher = None

HIDDEN = [
    "app.llm.providers.anthropic",
    "app.llm.providers.openai_compat",
    "app.tools.builtin.fs",
    "app.tools.builtin.exec",
    "app.tools.builtin.browser",
    "app.tools.builtin.docgen.docx_gen",
    "app.tools.builtin.docgen.pptx_gen",
    "app.tools.builtin.docgen.xlsx_gen",
    "app.tools.builtin.docgen.pdf_gen",
    "app.tools.builtin.ima",
    "app.tools.mcp.manager",
    "app.memory.long_term",
    "app.observability.metrics",
    "sqlite_vec",
    "lark_oapi",
    "structlog",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
]

datas = []
# Runtime-loaded markdown is not collected from imports. An empty glob here
# silently ships a backend whose workforce decompose collapses to 1 task.
_prompts = (Path(SPECPATH) / ".." / ".." / "backend" / "app" / "agents" / "prompts").resolve()
if not (_prompts / "planner.md").is_file():
    raise RuntimeError(f"planner.md missing at {_prompts}")
datas += [(str(_prompts), "app/agents/prompts")]
binaries = collect_dynamic_libs("sqlite_vec")
tmp_vec = collect_all("sqlite_vec")
datas += tmp_vec[0]
binaries += tmp_vec[1]
HIDDEN += tmp_vec[2]
tmp_ret = collect_all("lark_oapi")
datas += tmp_ret[0]
binaries += tmp_ret[1]
HIDDEN += tmp_ret[2]
tmp_browser = collect_all("playwright")
datas += [
    item for item in tmp_browser[0]
    if "/.local-browsers/" not in item[0].replace("\\", "/")
]
binaries += [
    item for item in tmp_browser[1]
    if "/.local-browsers/" not in item[0].replace("\\", "/")
]
HIDDEN += tmp_browser[2]

a = Analysis(
    ["..\\..\\backend\\app\\main.py"],
    pathex=["..\\..\\backend"],
    binaries=binaries,
    datas=datas,
    hiddenimports=HIDDEN,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
a.binaries = [item for item in a.binaries if "/.local-browsers/" not in item[0].replace("\\", "/")]
a.datas = [item for item in a.datas if "/.local-browsers/" not in item[0].replace("\\", "/")]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="python",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="python_runtime",
)
