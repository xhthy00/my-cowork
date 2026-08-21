"""Office-file scan for completion gating (no process-file cleanup)."""

from __future__ import annotations

import os
import time
from pathlib import Path

from app.workspace.output_files import list_new_office_files


class TestListNewOfficeFiles:
    def test_finds_untracked_new_docx(self, tmp_path: Path):
        workdir = tmp_path / "work"
        workdir.mkdir()
        old = workdir / "方案A.md"
        old.write_text("old", encoding="utf-8")
        past = time.time() - 60
        os.utime(old, (past, past))

        started = time.time()
        tracked = workdir / "方案B.docx"
        tracked.write_bytes(b"PK")
        report = workdir / "方案对比综合评审报告.docx"
        report.write_bytes(b"PK")
        (workdir / "notes.md").write_text("not office", encoding="utf-8")
        (workdir / "script.py").write_text("print(1)", encoding="utf-8")

        found = list_new_office_files(
            workdir, min_mtime=started, already=[str(tracked)]
        )
        names = {Path(p).name for p in found}
        assert "方案对比综合评审报告.docx" in names
        assert "方案B.docx" not in names
        assert "方案A.md" not in names
        assert "notes.md" not in names
        assert "script.py" not in names

    def test_skips_venv_and_camel_logs(self, tmp_path: Path):
        workdir = tmp_path / "work"
        hidden = workdir / "camel_logs"
        hidden.mkdir(parents=True)
        (hidden / "run.docx").write_bytes(b"PK")
        venv = workdir / ".venv" / "lib"
        venv.mkdir(parents=True)
        (venv / "x.docx").write_bytes(b"PK")
        found = list_new_office_files(workdir, min_mtime=time.time() - 10)
        assert found == []

    def test_ignores_old_office_file(self, tmp_path: Path):
        workdir = tmp_path / "work"
        workdir.mkdir()
        old = workdir / "old.docx"
        old.write_bytes(b"PK")
        past = time.time() - 60
        os.utime(old, (past, past))
        found = list_new_office_files(workdir, min_mtime=time.time())
        assert found == []
