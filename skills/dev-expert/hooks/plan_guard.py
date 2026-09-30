#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PreToolUse hook (GLOBAL): 改核心目录前强制要求存在进行中 *_plan.md（对齐 Rules §13）。

- 对落在「核心/危险目录」的源码文件写操作拦截；tests/、Plan/、依赖/资源目录不拦。
- 拦截条件：目标在核心目录 且 其 workspace 的 Plan/ 下无任何状态为 规划中/进行中 的 *_plan.md。
- 放行条件（有意例外）：workspace 未建立 Plan/ 目录（无 Plan 体系）时自动放行，避免误伤不采用本工作流的项目。此行为与「强制规划」措辞一致——§13 面向已采用 Plan 体系的项目。
- 命中 exit 2 阻断，提示先建计划（Trivial Fix 通道见 Rules §14，但核心目录改动仍强制规划）。

可配置（环境变量，分号分隔，未设置时用默认值）：
- PLAN_GUARD_CORE_DIRS：核心目录名集合，默认 src;app;lib;core;internal;system;engine
- PLAN_GUARD_EXCLUDE_DIRS：排除目录名集合，默认 tests;Plan;backup;vendor;node_modules;uploads;.codebuddy;dist;build;public;static;assets;test;__pycache__;.git
- PLAN_GUARD_TARGET_EXTS：拦截的文件扩展名，默认 .php;.js;.ts;.jsx;.tsx;.py;.java;.go;.vue

CMS 项目（如帝国CMS）需设置：
- PLAN_GUARD_CORE_DIRS=e/class;e/data;e/config;e/mods;e/member;e/template;e/admin
"""
import sys
import os
import json
import re

def _split_env(name, default):
    """从环境变量读取分号分隔的集合，未设置时用默认值。"""
    val = os.environ.get(name, "")
    if not val.strip():
        return default
    return set(p.strip() for p in val.split(";") if p.strip())

# 核心目录：可通过 PLAN_GUARD_CORE_DIRS 配置；默认为通用源码根目录
CORE_DIRS = _split_env(
    "PLAN_GUARD_CORE_DIRS",
    {"src", "app", "lib", "core", "internal", "system", "engine"},
)
# 排除目录：可通过 PLAN_GUARD_EXCLUDE_DIRS 配置；默认为通用排除集合
EXCLUDE_DIRS = _split_env(
    "PLAN_GUARD_EXCLUDE_DIRS",
    {
        "tests", "test", "Plan", "backup", "vendor", "node_modules",
        "uploads", ".codebuddy", "dist", "build", "public",
        "static", "assets", "__pycache__", ".git",
    },
)
# 拦截的扩展名：可通过 PLAN_GUARD_TARGET_EXTS 配置
TARGET_EXTS = _split_env(
    "PLAN_GUARD_TARGET_EXTS",
    {".php", ".js", ".ts", ".jsx", ".tsx", ".py", ".java", ".go", ".vue"},
)

# 状态标题行：兼容两种写法，与 handoff_snapshot.py 判定统一。
#   ①「## 状态」独占一行、状态值写在下一行（§13 canonical 模板）
#   ②「## 状态: 进行中」状态值同行带在冒号后（delivery-assurance.md 写法）
# 不再用严格正则锚定行尾，避免漏匹配「同行带值」格式导致误拦。


def find_workspace(path):
    """向上找含 Plan/ 子目录的祖先目录作为 workspace。"""
    d = os.path.dirname(path)
    while True:
        if os.path.isdir(os.path.join(d, "Plan")):
            return d
        nd = os.path.dirname(d)
        if nd == d:
            return None
        d = nd


def has_active_plan(workspace):
    """Plan/*.md 中存在状态为 规划中/进行中 的计划即视为激活。

    状态值可落在「## 状态」同行（## 状态: 进行中）或下一行（§13 canonical 模板），
    两种写法均识别，与 handoff_snapshot.py 的 startswith("## 状态") 判定保持一致。
    """
    plan_dir = os.path.join(workspace, "Plan")
    if not os.path.isdir(plan_dir):
        return False
    for fn in os.listdir(plan_dir):
        if not fn.endswith("_plan.md"):
            continue
        p = os.path.join(plan_dir, fn)
        try:
            with open(p, encoding="utf-8", errors="ignore") as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped.startswith("## 状态"):
                continue
            # 状态值可同行，或标题后隔空行/说明行出现；向后扫到下一个「## 」标题为止
            for j in range(i, min(i + 4, len(lines))):
                if j != i and lines[j].strip().startswith("## "):
                    break  # 已越过下一个标题，本段无激活状态
                if re.search(r'(规划中|进行中)', lines[j]):
                    return True
    return False


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
    ext = os.path.splitext(path)[1].lower()
    if ext not in TARGET_EXTS:
        return 0

    norm = path.replace("\\", "/").lower()
    parts = norm.split("/")
    # 排除非核心/资源/临时目录
    if any(part in EXCLUDE_DIRS for part in parts):
        return 0
    # 是否落在核心目录
    in_core = any(
        ("/%s/" % d) in norm or norm.endswith("/%s" % d) for d in CORE_DIRS
    )
    if not in_core:
        return 0

    workspace = find_workspace(path)
    if workspace is None:
        return 0  # 无 Plan 体系则不拦

    if has_active_plan(workspace):
        return 0

    print("[PLAN-GUARD] 拦截：改动核心目录前须先存在进行中的 *_plan.md（Rules §13）")
    print("目标: %s" % path)
    print("请在 Plan/ 下创建状态为「规划中/进行中」的 *_plan.md 后再改。")
    return 2  # 阻断


if __name__ == "__main__":
    sys.exit(main())
