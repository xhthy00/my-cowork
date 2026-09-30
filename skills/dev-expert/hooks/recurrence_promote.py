#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recurrence>=3 自动 promote 建议（草案）。

扫描 error_index.md，定位每条 ERR 对应的单条 .md（errors/ERR-XXX.md），
解析其中 Recurrence-Count / First-Seen / Last-Seen / Tasks 字段，
评估是否满足 promote 硬规则：
    Recurrence-Count >= 3 且 跨 >= 2 个不同任务(Tasks>=2) 且 在 30 天窗口内
满足则输出「建议 promote 到项目级 Agent 记忆文件（CLAUDE.md / AGENTS.md / project_memory.md；具体项目的规则文件名不同则用 --target 覆盖）」。

仅输出建议，不自动改写规则文件（遵守 dev-expert「改规则需用户确认」+ 不跨项目写禁忌）。
若单条 .md 尚未含 Recurrence 字段（error-ledger 模板未扩展），优雅跳过并提示。

退出码：
  0 = 完成（无论有无建议）
  2 = 索引缺失
"""
import sys
import os
import re
import argparse
from datetime import datetime

RECURRENCE_THRESHOLD = 3
MIN_TASKS = 2
WINDOW_DAYS = 30


def parse_index(path):
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        print("[RECUR-PROMOTE] 错误：读取索引失败: %s" % e, file=sys.stderr)
        return None
    for line in lines:
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5 or not re.match(r"^ERR-\d+$", cells[0]):
            continue
        rows.append({
            "err_id": cells[0],
            "desc": cells[1] if len(cells) > 1 else "",
            "keywords": cells[3] if len(cells) > 3 else "",
            "date": cells[4] if len(cells) > 4 else "",
        })
    return rows


def parse_recurrence(md_path):
    try:
        with open(md_path, encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return None

    def field(name):
        m = re.search(r"\*{0,2}%s\*{0,2}\s*[:：]\s*(\S+)" % re.escape(name), content)
        return m.group(1).strip() if m else None

    return {
        "count": field("Recurrence-Count"),
        "first": field("First-Seen"),
        "last": field("Last-Seen"),
        "tasks": field("Tasks"),
    }


def to_int(v):
    try:
        return int(str(v))
    except Exception:
        return 0


def to_date(v):
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(str(v), fmt)
        except Exception:
            continue
    return None


def main():
    parser = argparse.ArgumentParser(description="Recurrence>=3 promote 建议（草案）")
    parser.add_argument("--index", required=True, help="error_index.md 路径")
    parser.add_argument(
        "--errors-dir", default="",
        help="单条 ERR-XXX.md 目录（默认：索引同目录的 errors/）",
    )
    parser.add_argument(
        "--target", default="CLAUDE.md / AGENTS.md / project_memory.md（项目级记忆；具体项目的规则文件名不同则用 --target 覆盖）",
        help="建议 promote 的目标（默认项目级 Agent 记忆；若项目用特定规则文件如 主规则.mdc，用 --target 覆盖）",
    )
    args = parser.parse_args()

    rows = parse_index(args.index)
    if rows is None:
        return 2
    if not rows:
        print("[RECUR-PROMOTE] 索引无 ERR 条目")
        return 0

    errors_dir = args.errors_dir or os.path.join(os.path.dirname(args.index), "errors")
    today = datetime.now()
    suggestions = 0
    print("[RECUR-PROMOTE] 扫描 %d 条 ERR，硬规则：>=%d次 / >=%d任务 / %d天窗口"
          % (len(rows), RECURRENCE_THRESHOLD, MIN_TASKS, WINDOW_DAYS))
    for r in rows:
        md_path = os.path.join(errors_dir, r["err_id"] + ".md")
        rc = parse_recurrence(md_path)
        if not rc or rc["count"] is None:
            continue  # 字段未扩展，跳过
        count = to_int(rc["count"])
        tasks = to_int(rc["tasks"])
        last = to_date(rc["last"]) or to_date(r["date"])
        in_window = (today - last).days <= WINDOW_DAYS if last else False
        ok = count >= RECURRENCE_THRESHOLD and tasks >= MIN_TASKS and in_window
        tag = "[PROMOTE]" if ok else "[skip]"
        print("[RECUR-PROMOTE] %s %s | count=%s tasks=%s last=%s window=%s"
              % (r["err_id"], tag, count, tasks, rc["last"] or r["date"], in_window))
        if ok:
            suggestions += 1
            print("      → 建议写入 %s：防重踩规则（来自 %s：%s）"
                  % (args.target, r["err_id"], r["desc"]))
    print("[RECUR-PROMOTE] 共 %d 条满足 promote 条件" % suggestions)
    return 0


if __name__ == "__main__":
    sys.exit(main())
