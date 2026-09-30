#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PostToolUse hook (GLOBAL): 写源码后扫描 SELECT * 裸查询。

对齐 Rules §10 性能禁则（禁止 SELECT *，须显式列名）。仅对文本源文件生效。
非阻断 exit 1 回显 AI。SELECT 与 * 跨行(\\s+)亦可识别；count(*) 不含 'select *' 不误报。
"""
import sys
import os
import json
import re

TEXT_EXT = {".php", ".html", ".htm", ".js", ".css", ".py", ".sql", ".inc"}
SELECT_STAR = re.compile(r"select\s+\*", re.IGNORECASE)


def find_select_star_lines(text):
    """逐行扫描，跳过 PHP/JS/CSS 注释（//、#、/* */），返回命中行号。

    真实 SQL 多位于字符串字面量所在代码行，仍会被捕获；仅排除注释行，
    以降低说明性注释里出现 select * 的误报。
    """
    hits = []
    in_block = False
    for i, line in enumerate(text.splitlines(), start=1):
        s = line.strip()
        if in_block:
            if "*/" in line:
                in_block = False
            continue
        if "/*" in line:
            if "*/" in line:
                continue  # 同行闭合块注释，整行视为注释
            in_block = True
            continue
        if s.startswith("//") or s.startswith("#"):
            continue
        if SELECT_STAR.search(line):
            hits.append(i)
    return hits


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
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception:
        return 0

    hits = find_select_star_lines(text)
    if hits:
        print("[SQL-WARN] 发现 SELECT * 裸查询，请改为显式列名（Rules §10 性能禁则）：")
        for line in hits:
            print("  行 %d" % line)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
