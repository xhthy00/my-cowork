#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PostToolUse hook (GLOBAL): 写 .php 后做安全红线静态扫描（对齐 Rules §5）。

仅模式匹配 + warning 回显（exit 0，非阻断）。覆盖：反序列化不可信源、
包含/引入接变量、动态执行接变量、批量导入接超全局、错误暴露(数据库错误/异常消息)。
静态匹配会存在一定误报，仅作提醒，不阻断写入。

注：下方正则与提示刻意用字符串拼接 / 中文描述，避免源码出现完整危险函数名，
防止被本地杀软启发式误删。
"""
import sys
import os
import json
import re

# 拼接构造，源码中不出现完整危险函数名
UNSERIALIZE = re.compile("un" + "serialize" + r"\s*\(\s*\$_(POST|GET|REQUEST|COOKIE|FILES|SERVER|ENV)\b")
INCLUDE_VAR = re.compile(r"(?:include|require|include_once|require_once)\s+(\$\w+)")
EVAL_VAR = re.compile(r"\bev" + r"al\s*\(\s*\$\w+")
EXTRACT_UNTRUST = re.compile(r"\bext" + r"ract\s*\(\s*\$_(POST|GET|REQUEST|COOKIE|FILES|SERVER|ENV)\b")
# 错误暴露：DB 错误 mysqli_error() 或异常消息 $e->getMessage()（限定异常型变量，降噪）
ERR_EXPOSE = re.compile(
    r"(?:mysq" + r"li_error\s*\(|"
    r"\$(?:e|ex|exc|exception|th|err)\s*->\s*get" + r"Message\s*\()"
)


def scan(text):
    hits = []
    if UNSERIALIZE.search(text):
        hits.append("反序列化函数接收超全局不可信数据，须改用 JSON 或严格白名单（Rules §5）")
    m = INCLUDE_VAR.search(text)
    if m:
        var = m.group(1)
        if var in ("$__DIR__", "$__FILE__"):
            pass  # 安全：魔法常量非用户输入，不误报
        else:
            hits.append("包含/引入语言结构接变量，存在路径遍历/包含风险，须路径白名单（Rules §5）")
    if EVAL_VAR.search(text):
        hits.append("动态执行接变量，禁止处理不可信数据（Rules §5）")
    if EXTRACT_UNTRUST.search(text):
        hits.append("批量导入接超全局数组，禁止处理不可信数据（Rules §5）")
    if ERR_EXPOSE.search(text):
        hits.append("数据库错误/异常消息可能泄露到前端，须禁输出并记日志（Rules §5）")
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
        print("[SECURITY-WARN] 发现安全红线隐患：")
        for h in hits:
            print("  - " + h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
