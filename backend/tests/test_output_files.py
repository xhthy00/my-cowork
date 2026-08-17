"""Tests for deliverable vs process file classification and cleanup."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from app.workspace.output_files import (
    cleanup_process_files,
    is_deliverable_basename,
    is_deliverable_output_path,
    is_process_output_path,
    list_new_deliverables,
)


class TestIsDeliverableOutputPath:
    def test_report_docx(self):
        assert is_deliverable_output_path("/tmp/proj/report.docx")

    def test_png(self):
        assert is_deliverable_output_path("/tmp/proj/chart.png")

    def test_md(self):
        assert is_deliverable_output_path("/Users/me/out/summary.md")

    def test_scratch_dir(self):
        assert not is_deliverable_output_path("/tmp/proj/_scratch/x.md")

    def test_scratch_basename_still_deliverable(self):
        assert is_deliverable_basename("前十名深度分析报告.docx")
        assert not is_deliverable_output_path(
            "/tmp/proj/_scratch/前十名深度分析报告.docx"
        )

    def test_html_part(self):
        assert not is_deliverable_output_path("/tmp/proj/html_part1.html")

    def test_skeleton(self):
        assert not is_deliverable_output_path("/tmp/proj/page_skeleton.html")

    def test_py(self):
        assert not is_deliverable_output_path("/tmp/proj/script.py")

    def test_json(self):
        assert not is_deliverable_output_path("/tmp/proj/data.json")

    def test_requirements(self):
        assert not is_deliverable_output_path("/tmp/proj/requirements.txt")

    def test_dotfile(self):
        assert not is_deliverable_output_path("/tmp/proj/.gitignore")

    @pytest.mark.parametrize(
        "name",
        [
            "t_nf_0.0.xlsx",
            "t_comb1.xlsx",
            "t_h2.xlsx",
            "tC.xlsx",
            "t_nf_#,##0.0.xlsx",
            "t_nf_0.0%.xlsx",
            "t_nf_$#,##0.xlsx",
            "x1_check.xlsx",
            "tmp_build.xlsx",
            "demo.pptx",
        ],
    )
    def test_probe_and_format_token_files_are_not_deliverables(self, name):
        assert not is_deliverable_output_path(f"/tmp/proj/{name}")

    @pytest.mark.parametrize(
        "name",
        [
            "发货单列表2025_12.xlsx",
            "2025年12月发货单_销售与财务分析.xlsx",
            "table_销售.xlsx",
            "report.docx",
            "趋势图.png",
        ],
    )
    def test_real_deliverables_survive_probe_heuristic(self, name):
        assert is_deliverable_output_path(f"/tmp/proj/{name}")


class TestIsProcessOutputPath:
    def test_inverse(self):
        assert is_process_output_path("/tmp/proj/draft_notes.txt")
        assert not is_process_output_path("/tmp/proj/final.pptx")


class TestCleanupProcessFiles:
    def test_removes_scratch_and_process_keeps_deliverable(self, tmp_path: Path):
        workdir = tmp_path / "work"
        scratch = workdir / "_scratch"
        scratch.mkdir(parents=True)
        (scratch / "tmp.md").write_text("x", encoding="utf-8")
        part = workdir / "html_part1.html"
        part.write_text("<html/>", encoding="utf-8")
        report = workdir / "report.docx"
        report.write_bytes(b"PK")
        outside = tmp_path / "outside_scratch.txt"
        outside.write_text("keep", encoding="utf-8")

        cleaned, rescued = cleanup_process_files(
            workdir,
            [part, report, outside, scratch / "tmp.md"],
        )

        assert not scratch.exists()
        assert not part.exists()
        assert report.exists()
        assert outside.exists()
        assert rescued == []
        assert any("html_part1.html" in p for p in cleaned)
        assert any("_scratch" in p.replace("\\", "/") for p in cleaned)

    def test_rescues_deliverable_from_scratch(self, tmp_path: Path):
        workdir = tmp_path / "work"
        scratch = workdir / "_scratch"
        scratch.mkdir(parents=True)
        misplaced = scratch / "2026届高三(7)班_一模数学_前十名深度分析报告.docx"
        misplaced.write_bytes(b"PK\x03\x04rescue")
        (scratch / "notes.txt").write_text("tmp", encoding="utf-8")

        cleaned, rescued = cleanup_process_files(workdir, [misplaced])

        assert not scratch.exists()
        dest = workdir / "2026届高三(7)班_一模数学_前十名深度分析报告.docx"
        assert dest.exists()
        assert dest.read_bytes() == b"PK\x03\x04rescue"
        assert any(dest.name in p for p in rescued)
        assert not any(dest.name in p for p in cleaned)

    def test_rescue_avoids_overwrite(self, tmp_path: Path):
        workdir = tmp_path / "work"
        scratch = workdir / "_scratch"
        scratch.mkdir(parents=True)
        existing = workdir / "report.docx"
        existing.write_bytes(b"old")
        (scratch / "report.docx").write_bytes(b"new")

        _cleaned, rescued = cleanup_process_files(workdir, [])

        assert existing.read_bytes() == b"old"
        alt = workdir / "report_1.docx"
        assert alt.exists()
        assert alt.read_bytes() == b"new"
        assert any(alt.name in p for p in rescued)

    def test_ignores_paths_outside_workdir(self, tmp_path: Path):
        workdir = tmp_path / "work"
        workdir.mkdir()
        outsider = tmp_path / "script.py"
        outsider.write_text("print(1)", encoding="utf-8")
        cleaned, rescued = cleanup_process_files(workdir, [outsider])
        assert outsider.exists()
        assert cleaned == []
        assert rescued == []

    def test_cleans_probe_xlsx_but_keeps_real_deliverable(self, tmp_path: Path):
        workdir = tmp_path / "work"
        workdir.mkdir()
        probe1 = workdir / "t_nf_0.0.xlsx"
        probe2 = workdir / "t_comb1.xlsx"
        probe1.write_bytes(b"PK")
        probe2.write_bytes(b"PK")
        final = workdir / "2025年12月发货单_销售与财务分析.xlsx"
        final.write_bytes(b"PK")

        cleaned, rescued = cleanup_process_files(
            workdir, [probe1, probe2, final]
        )

        assert not probe1.exists()
        assert not probe2.exists()
        assert final.exists()
        assert rescued == []
        assert any("t_nf_0.0.xlsx" in p for p in cleaned)
        assert any("t_comb1.xlsx" in p for p in cleaned)


class TestListNewDeliverables:
    def test_finds_untracked_new_docx(self, tmp_path: Path):
        workdir = tmp_path / "work"
        scratch = workdir / "_scratch"
        scratch.mkdir(parents=True)
        old = workdir / "方案A.md"
        old.write_text("old", encoding="utf-8")
        past = time.time() - 60
        os.utime(old, (past, past))

        started = time.time()
        tracked = workdir / "方案B.md"
        tracked.write_text("tracked", encoding="utf-8")
        report = workdir / "方案对比综合评审报告.docx"
        report.write_bytes(b"PK")
        (scratch / "tmp.md").write_text("scratch", encoding="utf-8")
        (workdir / "notes.txt").write_text("not a deliverable", encoding="utf-8")

        found = list_new_deliverables(
            workdir, min_mtime=started, already=[str(tracked)]
        )
        names = {Path(p).name for p in found}
        assert "方案对比综合评审报告.docx" in names
        assert "方案B.md" not in names
        assert "方案A.md" not in names
        assert "tmp.md" not in names
        assert "notes.txt" not in names
