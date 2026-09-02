#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PostToolUse hook (GLOBAL): 写源码后校验文件为合法 UTF-8。

对齐 Rules §8：本环境 PHP 默认 UTF-8，Windows 下误用 GBK 保存会静默损坏中文。
仅对文本类源文件生效。非阻断：发现非 UTF-8 时 exit 1（warning 回显 AI）。
其他故障静默 exit 0。
"""
import sys
import os
import json

TEXT_EXT = {".php", ".html", ".htm", ".js", ".css", ".json", ".py", ".md",
            ".txt", ".xml", ".sql", ".conf", ".ini", ".cfg"}


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
    if not os.path.isfile(path):
        return 0

    try:
        with open(path, "rb") as f:
            data_bytes = f.read()
    except Exception:
        return 0

    try:
        data_bytes.decode("utf-8")
    except UnicodeDecodeError:
        print("[UTF8-WARN] 文件不是合法 UTF-8 编码（可能是 GBK 损坏），请转 UTF-8 保存（Rules §8）")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
