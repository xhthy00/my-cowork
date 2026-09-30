#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PostToolUse hook (GLOBAL): 写 PHP 文件后做语法自检。

后端 php -l：本环境 php -l 对语法错误返回退出码 0（异常），但 stdout 明确含
"Parse error" / "Errors parsing"。故以【输出字符串】判定（非退出码），对真实项目路径可靠闭环。
hook 跑的是工作区内真实文件（非 tempfile），故输出判定稳定。
- 仅对 .php 文件生效。
- 非阻塞：发现语法错误时 exit 1（warning，回显 AI），不阻断已完成的写入。
- 其他故障（如 php 找不到）静默 exit 0，避免误报卡住工作。
"""
import sys
import os
import json
import shutil
import subprocess

# PHP 可执行文件探测协议（对齐 references/cms-development.md「PHP 可执行文件探测协议」）：
# 严禁硬编码唯一路径，按优先级链解析，换机/换用户/跨平台可用。
_WIN_CANDIDATES = [
    r"F:\BtSoft\php\{ver}\php.exe",
    r"D:\phpstudy\php\{ver}\php.exe",
    r"C:\xampp\php\php.exe",
    r"C:\Program Files\php\php.exe",
]
_MAC_CANDIDATES = [
    "/opt/homebrew/bin/php@{ver}",
    "/usr/local/bin/php@{ver}",
    "/Applications/MAMP/bin/php/php{ver}/bin/php",
]
_LIN_CANDIDATES = [
    "/usr/bin/php{ver}",
    "/usr/local/bin/php{ver}",
    "/opt/php/{ver}/bin/php",
]
# 版本号高到低探测（含本机 F:\BtSoft\php\85 等）
_VERSIONS = ["85", "84", "83", "82", "81", "80", "74"]


def resolve_php():
    """按探测协议解析 PHP 可执行文件路径；全部未命中返回 None（调用方静默跳过）。"""
    env = os.environ.get("PHP_BIN")
    if env and os.path.isfile(env):
        return env
    # 多版本环境变量（PHP_85 / PHP_82 ...）
    for ver in _VERSIONS:
        envv = os.environ.get("PHP_" + ver)
        if envv and os.path.isfile(envv):
            return envv
    # 系统 PATH
    p = shutil.which("php")
    if p:
        return p
    # 常见安装位置自动扫描
    for tpl in _WIN_CANDIDATES + _MAC_CANDIDATES + _LIN_CANDIDATES:
        for ver in _VERSIONS:
            cand = tpl.format(ver=ver)
            if os.path.isfile(cand):
                return cand
    return None


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

    php_bin = resolve_php()
    if not php_bin:
        # PHP 不可解析（未配置 PHP_BIN 且不在 PATH/常见位置）：静默跳过，避免误报卡住工作
        return 0

    try:
        r = subprocess.run(
            [php_bin, "-l", path],
            capture_output=True, text=True, timeout=30,
        )
    except Exception:
        return 0

    out = (r.stdout or "") + (r.stderr or "")
    # 本环境 php -l 退出码对语法错误仍为 0（异常），但 stdout 含 Parse error 可靠。
    # 成功信息 "No syntax errors detected" 不含 "Parse error"，不会误判。
    if "Parse error" in out or "Errors parsing" in out:
        print("[LINT-FAIL] php -l 发现语法错误：")
        print(out.strip())
        return 1  # warning，回显给 AI
    return 0


if __name__ == "__main__":
    sys.exit(main())
