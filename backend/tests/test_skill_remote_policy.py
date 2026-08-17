"""Tests for skill_usable_via_remote."""

from app.guardrails.policy import skill_usable_via_remote


def test_fs_write_skill_not_remote_usable():
    assert skill_usable_via_remote({"allowed_tools": ["builtin.fs.write"]}) is False


def test_http_request_skill_is_remote_usable():
    assert skill_usable_via_remote({"allowed_tools": ["builtin.http.request"]}) is True


def test_docx_skill_not_remote_usable():
    assert skill_usable_via_remote({"allowed_tools": ["builtin.docx.gen"]}) is False


def test_empty_whitelist_remote_usable():
    assert skill_usable_via_remote({"allowed_tools": []}) is True
