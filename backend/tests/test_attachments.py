from pathlib import Path

from app.runtime.attachments import (
    extract_attachment_paths,
    stage_attachments_for_task,
)
from app.sandbox.path_guard import PathGuard


def test_extract_attachment_paths():
    text = "解读\n\n[附件: /tmp/a.docx, /tmp/b.txt]"
    assert extract_attachment_paths(text) == ["/tmp/a.docx", "/tmp/b.txt"]


def test_stage_copies_and_whitelists(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    src = src_dir / "note.txt"
    src.write_text("hello", encoding="utf-8")
    workdir = tmp_path / "work"
    workdir.mkdir()
    guard = PathGuard([str(workdir)])

    text = f"请解读\n\n[附件: {src}]"
    out = stage_attachments_for_task(text, workdir, guard)
    staged = workdir / "attachments" / "note.txt"
    assert staged.is_file()
    assert staged.read_text(encoding="utf-8") == "hello"
    assert str(staged.resolve()) in out
    guard.check_path(str(staged))


def test_stage_filename_only_adds_system_note(tmp_path):
    workdir = tmp_path / "work"
    workdir.mkdir()
    out = stage_attachments_for_task(
        "看这个\n\n[附件: 方案.docx]",
        workdir,
        PathGuard([str(workdir)]),
    )
    assert "缺少绝对路径" in out
    assert "系统" in out
