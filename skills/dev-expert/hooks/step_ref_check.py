#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨文件步骤号一致性检查器。

扫描 SKILL.md / README.md / FAQ.md 中所有形如「<reference名> 第<中文数字>步」的引用，
比对目标 reference 文件实际「### 第N步」章节号，报告不匹配项。

用于防止步骤号漂移（如 v1.9.0 新增「第二步点五」导致后续步骤号 +1 后，
历史变更日志/FAQ 中的步骤号引用未同步更新）。

用法：
  python step_ref_check.py [--root <技能根目录>]

退出码：
  0 = 全部匹配
  1 = 发现不匹配或错误
"""
import argparse
import os
import re
import sys

# 中文数字映射
CN_NUM = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}

# 匹配「<reference名>.md ... 第<中文数字>步」或「`<reference名>` ... 第<中文数字>步」
# reference 名形如 software-project / code-generation / bug-diagnosis 等
REF_RE = re.compile(
    r'`?([a-z][a-z0-9-]+)(?:\.md)?`?[\s\S]{0,30}?第([一二三四五六七八九十]+)步'
)

# 匹配目标文件中的「### 第<N>步：」章节标题
STEP_HEAD_RE = re.compile(r'^###\s*第([一二三四五六七八九十]+)步', re.MULTILINE)

# 已知的 19 个子技能 reference 名（用于过滤误匹配；与 SKILL.md / README / FAQ 的"19 个子技能"口径一致）
KNOWN_REFS = {
    "software-project", "website-project", "api-design", "bug-diagnosis",
    "karpathy-coding-guidelines", "spec-driven-development", "code-review",
    "code-generation", "task-decomposition-and-execution", "tech-selection",
    "doc-generation", "test-generation", "performance-benchmark", "refactoring",
    "project-memory-management", "cms-development", "frontend-design",
    "mysql-database", "project-knowledge-graph",
}


def cn_to_int(cn):
    """中文数字转整数（支持一到九十九）。"""
    if cn == "十":
        return 10
    if cn.startswith("十"):
        return 10 + CN_NUM.get(cn[1:], 0)
    if cn.endswith("十"):
        return CN_NUM.get(cn[:-1], 0) * 10
    if "十" in cn:
        parts = cn.split("十")
        return CN_NUM.get(parts[0], 0) * 10 + CN_NUM.get(parts[1], 0)
    return CN_NUM.get(cn, 0)


def int_to_cn(n):
    """整数转中文数字（支持一到十）。"""
    cn_map = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五",
              6: "六", 7: "七", 8: "八", 9: "九", 10: "十"}
    return cn_map.get(n, str(n))


def find_step_heads(content):
    """在文件内容中查找所有「第N步」章节，返回步骤号集合。"""
    steps = {}
    for m in STEP_HEAD_RE.finditer(content):
        cn = m.group(1)
        n = cn_to_int(cn)
        if n > 0:
            steps[n] = cn
    return steps


def check_file(ref_root, src_path, src_name):
    """检查单个源文件中的所有步骤号引用。"""
    try:
        with open(src_path, encoding="utf-8") as f:
            content = f.read()
    except OSError as e:
        print("[STEP-CHECK] 错误：读取 %s 失败: %s" % (src_name, e), file=sys.stderr)
        return [], 0

    issues = []
    checked = 0
    seen = set()  # 去重：(ref, expected)
    for m in REF_RE.finditer(content):
        ref_name = m.group(1)
        cn_step = m.group(2)
        expected = cn_to_int(cn_step)
        # 只检查已知的 reference 名，过滤误匹配
        if ref_name not in KNOWN_REFS:
            continue
        key = (ref_name, expected)
        if key in seen:
            continue
        seen.add(key)
        ref_path = os.path.join(ref_root, "references", ref_name + ".md")
        if not os.path.isfile(ref_path):
            continue
        try:
            with open(ref_path, encoding="utf-8") as f:
                ref_content = f.read()
        except OSError:
            continue
        actual_steps = find_step_heads(ref_content)
        checked += 1
        if expected not in actual_steps:
            actual_str = "、".join(
                "第%s步" % actual_steps[k] for k in sorted(actual_steps)
            ) if actual_steps else "无步骤章节"
            issues.append({
                "src": src_name,
                "ref": ref_name,
                "expected_cn": cn_step,
                "expected_n": expected,
                "actual": actual_str,
                "context": m.group(0).replace("\n", " ")[:80],
            })
    return issues, checked


def _fix_stdout_encoding():
    """Windows 默认控制台为 GBK，直接 print emoji（✅/❌）会抛 UnicodeEncodeError。
    若 stdout 编码非 utf-8 且无缓冲能力，回退到对无法编码字符做替换，保证脚本不崩。"""
    try:
        if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") not in (
            "utf8", "utf8"
        ):
            import io
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace"
            )
    except Exception:
        pass


def main():
    _fix_stdout_encoding()
    parser = argparse.ArgumentParser(
        description="跨文件步骤号一致性检查器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--root",
        default=None,
        help="技能根目录（默认：脚本上级目录）",
    )
    args = parser.parse_args()
    root = args.root or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    )
    refs_dir = os.path.join(root, "references")
    if not os.path.isdir(refs_dir):
        print("[STEP-CHECK] 错误：references 目录不存在: %s" % refs_dir, file=sys.stderr)
        return 1

    src_files = ["SKILL.md", "README.md", "FAQ.md"]
    all_issues = []
    total_checked = 0
    for src in src_files:
        src_path = os.path.join(root, src)
        if not os.path.isfile(src_path):
            continue
        issues, checked = check_file(root, src_path, src)
        all_issues.extend(issues)
        total_checked += checked

    print("[STEP-CHECK] 检查完成：扫描 %d 处步骤号引用" % total_checked)
    if not all_issues:
        print("[STEP-CHECK] ✅ 全部匹配")
        return 0
    print("[STEP-CHECK] ❌ 发现 %d 处不匹配：" % len(all_issues))
    for i, issue in enumerate(all_issues, 1):
        print("  %d. [%s] %s 期望 第%s步(%d)，实际 %s" % (
            i, issue["src"], issue["ref"],
            issue["expected_cn"], issue["expected_n"], issue["actual"]
        ))
        print("     上下文: %s" % issue["context"])
    return 1


if __name__ == "__main__":
    sys.exit(main())
