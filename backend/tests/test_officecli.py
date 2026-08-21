"""Tests for officecli resolve + watch manager (mocked) + assistants seed."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.assistants import load_assistants
from app.tools.officecli.resolve import probe_watch, resolve_officecli
from app.tools.officecli.watch_manager import WatchManager


def test_resolve_prefers_env_path(tmp_path, monkeypatch):
    fake = tmp_path / "officecli"
    fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("MY_COWORK_OFFICECLI", str(fake))
    with patch("app.tools.officecli.resolve.probe_watch", return_value=True):
        assert resolve_officecli() == fake


def test_resolve_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(
        "app.tools.officecli.resolve.Path.home", lambda: tmp_path
    )
    with patch("app.tools.officecli.resolve.shutil.which", return_value=None):
        assert resolve_officecli() is None


def test_probe_watch_false_on_nonzero():
    with patch("app.tools.officecli.resolve.subprocess.run") as run:
        run.return_value = MagicMock(returncode=1)
        assert probe_watch(Path("/fake/officecli")) is False


def test_probe_watch_true_on_zero():
    with patch("app.tools.officecli.resolve.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0)
        assert probe_watch(Path("/fake/officecli")) is True


def test_watch_manager_not_found(tmp_path):
    mgr = WatchManager(ready_timeout=0.5)
    with patch(
        "app.tools.officecli.watch_manager.resolve_officecli", return_value=None
    ):
        f = tmp_path / "deck.pptx"
        f.write_bytes(b"PK")
        out = mgr.start(str(f))
    assert out["error_code"] == "OFFICECLI_NOT_FOUND"


def test_assistants_builtin_seed(tmp_path):
    items = load_assistants(path=tmp_path / "missing.json")
    ids = {a["id"] for a in items}
    assert "ppt-creator" in ids
    assert "word-creator" in ids
    assert "dashboard-creator" in ids
    ppt = next(a for a in items if a["id"] == "ppt-creator")
    assert "officecli" in ppt["enabled_skills"]
    assert "officecli-pptx" in ppt["enabled_skills"]
    assert ppt.get("category") == "presentation"


def test_office_bypass_refuse_pandoc_docx():
    from app.runtime.v2.office import office_bypass_refuse

    assert office_bypass_refuse("which pandoc && pandoc --version") is None
    assert office_bypass_refuse("officecli create report.docx") is None
    msg = office_bypass_refuse("pandoc report.html -o /tmp/out.docx")
    assert msg and "pandoc" in msg.lower()
