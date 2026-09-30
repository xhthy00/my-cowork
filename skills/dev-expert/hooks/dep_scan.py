#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PostToolUse hook (GLOBAL): 依赖变更后提示漏洞扫描。

检测到依赖清单文件被修改时，输出对应包管理器的漏洞扫描命令提示，
帮助 AI 在安装/更新依赖后主动检测已知漏洞（npm audit / pip-audit / composer audit）。

触发文件：
  - package.json / package-lock.json → npm audit
  - requirements.txt / Pipfile / pyproject.toml → pip-audit
  - composer.json / composer.lock → composer audit
  - go.mod / go.sum → govulncheck
  - pom.xml → mvn dependency-check
  - Gemfile / Gemfile.lock → bundle audit

输出为提示信息（exit 0），不阻断执行；AI 应根据提示决定是否运行扫描。
"""
import sys
import os
import json

# 依赖文件 → 扫描命令映射
DEP_FILES = {
    "package.json": "npm audit --audit-level=moderate",
    "package-lock.json": "npm audit --audit-level=moderate",
    "yarn.lock": "yarn audit --level moderate",
    "pnpm-lock.yaml": "pnpm audit --audit-level moderate",
    "requirements.txt": "pip-audit -r requirements.txt",
    "pipfile": "pip-audit",
    "pipfile.lock": "pip-audit",
    "pyproject.toml": "pip-audit",
    "poetry.lock": "pip-audit",
    "composer.json": "composer audit",
    "composer.lock": "composer audit",
    "go.mod": "govulncheck ./...",
    "go.sum": "govulncheck ./...",
    "pom.xml": "mvn dependency-check:check",
    "gemfile": "bundle audit check",
    "gemfile.lock": "bundle audit check",
}


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

    basename = os.path.basename(path).lower()
    scan_cmd = DEP_FILES.get(basename)
    if not scan_cmd:
        return 0

    print("[DEP-SCAN] 检测到依赖文件变更: %s" % basename)
    print("建议执行漏洞扫描: %s" % scan_cmd)
    print("若存在已知漏洞，应在交付前在「已知限制/未验证项」中披露。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
