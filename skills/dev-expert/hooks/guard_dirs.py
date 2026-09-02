#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PreToolUse hook (GLOBAL): 拦截对数据/依赖目录的写操作。

对齐 Rules §5/§7.3：uploads(上传目录,禁手改源码)、backup(回滚存放)、
vendor/node_modules(依赖) 不应由 AI 直接编辑源码写入。命中即 exit 2 阻断。
- 仅检查目标文件路径本身所在目录，不误伤其父级正常目录。
- 输出清晰拒绝原因，便于 AI 立即感知并改向。
"""
import sys
import os
import json

# 禁止 AI 直接写入的目录（数据/依赖/回滚，大小写不敏感）
FORBIDDEN = {"uploads", "backup", "vendor", "node_modules"}


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

    norm = os.path.abspath(path).replace("\\", "/").lower()
    if any(part in FORBIDDEN for part in norm.split("/")):
        print("[GUARD-BLOCK] 拒绝写入受保护目录：%s" % path)
        print("该目录(uploads/backup/vendor/node_modules)不应由 AI 直接编辑源码，"
              "如确需改动请先在计划中明确并说明理由。")
        return 2  # 阻断
    return 0


if __name__ == "__main__":
    sys.exit(main())
