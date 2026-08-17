#!/usr/bin/env bash
# Re-vendor official-document-writing from upstream into resources/example-skills/.
# After running, review the diff and commit. Daily use does not need this script.
# Usage: bash scripts/vendor-official-document-skill.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/resources/example-skills/official-document-writing"
REPO_URL="${OFFICIAL_DOC_SKILL_REPO:-https://github.com/KaguraNanaga/official-document-writing-skill.git}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Cloning $REPO_URL …"
git clone --depth 1 "$REPO_URL" "$TMP/official-document-writing"
rm -rf "$TMP/official-document-writing/.git"

# Adapt for MyCowork: relative Base dir reads + Word deliverable via officecli.
python3 - <<'PY' "$TMP/official-document-writing"
from pathlib import Path
import sys

root = Path(sys.argv[1])
skill = root / "SKILL.md"
if not skill.is_file():
    raise SystemExit("SKILL.md missing after clone")

text = skill.read_text(encoding="utf-8")
marker = "## MyCowork 使用说明"
if marker not in text:
    insert = """## MyCowork 使用说明

本技能已内置于 MyCowork（技能 id：`official-document-writing`，助手名：「公文写作助手」）。

- 所有参考资料路径均相对于本技能 **Base directory**（`load_skill` 返回值中的路径）。用读文件 / `bash` 打开相对路径，例如 `references/document-templates.md`、`references/body-manuscript-format.md`、`checklists/quality-checklist.md`。不要使用 Codex/Claude 本机绝对路径。
- 需要交付 `.docx` 时：先按本技能完成文种、结构与用语，再严格按 `references/body-manuscript-format.md`（正文稿：方正字体、上下 3cm / 左右 2.9cm、固定行距 29 磅、页脚长线段页码）用 `officecli` 生成 Word。不要使用 officecli-docx 的商务报告默认字体/行距/封面/目录。`docx_gen` 仅作降级。
- **硬性要求**：用户说「生成 / 重新生成 / 写一份」时，必须在本轮用 `officecli`（或 `docx_gen`）写出一个新的 `.docx`。禁止只回复「已按规范重新生成」而不调用写文件工具；已有旧文件不算完成。不要加载通用 `docx` 技能。
- 本技能辅助撰写与质检，**不构成正式发文依据**；涉密、签发、编号与内部流程以用户单位规定为准。

"""
    # Insert after the first H1 body section title block (after frontmatter + intro heading).
    needle = "# 公文写作技能\n"
    if needle in text:
        text = text.replace(needle, needle + "\n" + insert, 1)
    else:
        # Fallback: after frontmatter closing ---
        parts = text.split("---", 2)
        if len(parts) >= 3:
            text = "---" + parts[1] + "---\n\n" + insert + parts[2].lstrip("\n")
        else:
            text = insert + text
    skill.write_text(text, encoding="utf-8")
    print("patched SKILL.md (MyCowork notes)")
else:
    print("SKILL.md already has MyCowork notes")
PY

rm -rf "$DEST"
mkdir -p "$(dirname "$DEST")"
mv "$TMP/official-document-writing" "$DEST"

OVERLAY="$ROOT/scripts/patches/official-document-writing"
if [[ -d "$OVERLAY" ]]; then
  cp -R "$OVERLAY/." "$DEST/"
  echo "applied local overlay from scripts/patches/official-document-writing"
fi

echo "Vendored → $DEST ($(du -sh "$DEST" | awk '{print $1}'))"
echo "Review and commit when ready."
