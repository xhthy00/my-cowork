#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PostToolUse hook (GLOBAL): 写源码后扫描调试残留。

对齐 Rules §10（错误闭环/勿留调试）：捕获 var_dump/print_r/var_export/die()/exit()/console.log。
仅对文本源文件生效，跳过 tests 目录（测试辅助允许）。非阻断 exit 1 回显 AI。
"""
import sys
import os
import json
import re

TEXT_EXT = {".php", ".html", ".htm", ".js", ".css", ".py", ".json", ".md", ".txt"}
DEBUG = re.compile(
    r"(?:var_dump|print_r|var_export|\bdie\b|(?<!\.)\bexit\b|console\s*\.\s*log)\s*\("
)


def main():
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return 0
        data = json.loads(raw)
    except Exception:
        return 0

    tool_input = data.get("tool_input", {}) or {}
    path = (
        tool_input.get("filePath")
        or tool_input.get("file_path")
        or tool_input.get("path")
        or ""
    )
    if not path:
        return 0
    path = os.path.abspath(path)
    if os.path.splitext(path)[1].lower() not in TEXT_EXT:
        return 0
    # 跳过测试目录，避免误报测试辅助代码
    if any(s.lower() in ("tests", "test") for s in path.split(os.sep)):
        return 0
    if not os.path.isfile(path):
        return 0

    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception:
        return 0

    hits = []
    for m in DEBUG.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        hits.append((line, m.group(0).strip()))
    if hits:
        print("[DEBUG-WARN] 发现调试残留，请确认是否应保留（Rules §10）：")
        for line, tok in hits:
            print("  行 %d: %s" % (line, tok))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
