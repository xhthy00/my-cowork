"""Shared notes toolkit tests."""

from pathlib import Path

from app.runtime.notes_context import NotesRuntime, reset_notes_runtime, set_notes_runtime
from app.tools.builtin.notes import append_note, create_note, list_note, read_note


def test_notes_roundtrip(tmp_path: Path):
    token = set_notes_runtime(NotesRuntime(task_id="t1", root=tmp_path))
    try:
        assert "no notes" in list_note()
        assert "Created" in create_note("shared_files", "/tmp/a.txt")
        assert "Appended" in append_note("shared_files", "/tmp/b.txt")
        body = read_note("shared_files")
        assert "/tmp/a.txt" in body
        assert "/tmp/b.txt" in body
        assert "shared_files" in list_note()
    finally:
        reset_notes_runtime(token)


def test_notes_without_runtime():
    assert "unavailable" in list_note()
