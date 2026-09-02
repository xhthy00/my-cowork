#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PostToolUse hook (GLOBAL): 写 .php 后做 PHP 8.x 兼容性静态扫描（对齐 Rules §6）。

仅做纯模式匹配（不依赖 php -l，因本环境 php -l 退出码不可信），命中即 warning 回显 AI，
非阻断（exit 0）。涵盖：短标签、裸数组键、each()/create_function()/get_magic_quotes_gpc()。
"""
import sys
import os
import json
import re

# <? 后非 php/=/xml 视为短标签（<?php / <?= / <?xml 合法）
SHORT_TAG = re.compile(r'<\?(?!(php|=|xml)\b)')
# $arr[key] 裸键（key 为字母开头、非 $ 变量、非引号、非纯数字）
BARE_KEY = re.compile(r'\$\w+\[([A-Za-z_][A-Za-z0-9_]*)\]')
BAD_FUNCS = [
    (re.compile(r'\beach\s*\('), 'each()'),
    (re.compile(r'\bcreate_function\s*\('), 'create_function()'),
    (re.compile(r'\bget_magic_quotes_gpc\s*\('), 'get_magic_quotes_gpc()'),
]


def scan(text):
    hits = []
    if SHORT_TAG.search(text):
        hits.append("短标签 <?（非 <?php/<?=/<?xml），须改 <?php")
    mk = BARE_KEY.search(text)
    if mk:
        key = mk.group(1)
        # 跳过全大写常量（如 $arr[MY_CONST]）及语言常量 true/false/null，
        # 避免误伤合法常量用法；§6 针对的是裸字符串键（小写/混合大小写）
        if key.isupper() or key.lower() in ("true", "false", "null"):
            pass
        else:
            hits.append("裸数组键 $arr[%s] 未加引号，须 $arr['%s']（Rules §6）" % (key, key))
    for rx, name in BAD_FUNCS:
        if rx.search(text):
            hits.append("已废弃函数 %s（PHP8 已移除），须替换（Rules §6）" % name)
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
        print("[PHP8-COMPAT-WARN] 发现 PHP8 兼容隐患：")
        for h in hits:
            print("  - " + h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
