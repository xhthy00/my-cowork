#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PostToolUse hook (GLOBAL): 写 .php 后做敏感信息静态扫描（对齐 Rules §5/§19）。

仅模式匹配 + warning 回显（exit 0，非阻断）。覆盖：硬编码明文凭证、
日志/文件写入含敏感变量。敏感词用拼接构造，避免被本地杀软启发式误删。
"""
import sys
import os
import json
import re

# 拼接构造，源码中不出现完整敏感词
CREDS = re.compile(
    "(pass" + "word|pass" + "_word|pass" + "wd|pwd|api" + "_key|sec" + "ret|tok" + "en|access" + "_key|db" + "pass|db" + "_pass)"
    r"\s*=\s*[\"'][^\"']{4,}[\"']"
)
LOG_FN = re.compile("(?:error" + "_log|sys" + "log|file" + "_put_contents)")
SENS_VAR = re.compile("(?:pass" + "word|tok" + "en|sec" + "ret|phone|mobile|api" + "_key)")


def scan(text):
    hits = []
    if CREDS.search(text):
        hits.append("疑似硬编码明文凭证(口令/密钥/令牌)，须配置外置或环境变量（Rules §5）")
    if LOG_FN.search(text) and SENS_VAR.search(text):
        hits.append("日志/文件写入可能含敏感变量(令牌/口令/手机号)，须脱敏（Rules §5/§19）")
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
    if os.path.splitext(path)[1].lower() != ".php":
        return 0
    if not os.path.isfile(path):
        return 0

    try:
        text = open(path, encoding="utf-8", errors="ignore").read()
    except Exception:
        return 0

    hits = scan(text)
    if hits:
        print("[SECRET-WARN] 发现敏感信息隐患：")
        for h in hits:
            print("  - " + h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
