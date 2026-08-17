#!/usr/bin/env bash
# Re-vendor china-legal-counsel from upstream into resources/example-skills/.
# After running, review the diff and commit. Daily use does not need this script.
# Usage: bash scripts/vendor-china-legal-skill.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/resources/example-skills/china-legal-counsel"
REPO_URL="${CHINA_LEGAL_SKILL_REPO:-https://github.com/Daknniel-0881/qulv-china-legal-counsel-skill.git}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Cloning $REPO_URL …"
git clone --depth 1 "$REPO_URL" "$TMP/china-legal-counsel"
rm -rf "$TMP/china-legal-counsel/.git"

# Patch Codex absolute paths in agent-facing docs.
python3 - <<'PY' "$TMP/china-legal-counsel"
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
replacements = [
    (
        re.compile(
            r"- Use the bundled local knowledge base at `knowledge-base/` inside this skill\. "
            r"Resolve it as `/Users/suze/\.codex/skills/china-legal-counsel/knowledge-base` in this local install\."
        ),
        "- Use the bundled local knowledge base at `knowledge-base/` inside this skill "
        "(relative to this skill's Base directory). Do **not** use Codex/home absolute paths.\n"
        "- Run KB scripts from this skill's Base directory, e.g. "
        '`python3 scripts/kb_search.py "格式条款 说明义务" --limit 5`. '
        "Pass `--kb knowledge-base` only when needed; default is the bundled folder.",
    ),
    (
        re.compile(
            r"Local install path: `/Users/suze/\.codex/skills/china-legal-counsel/knowledge-base`\n?"
        ),
        "Run scripts from the skill root; do not hard-code Codex/home absolute paths.\n",
    ),
]
for path in [root / "SKILL.md", root / "references" / "source-registry.md"]:
    if not path.is_file():
        continue
    text = path.read_text(encoding="utf-8")
    orig = text
    for pat, repl in replacements:
        text = pat.sub(repl, text)
    if text != orig:
        path.write_text(text, encoding="utf-8")
        print(f"patched {path.relative_to(root)}")
PY

rm -rf "$DEST"
mkdir -p "$(dirname "$DEST")"
mv "$TMP/china-legal-counsel" "$DEST"
echo "Vendored → $DEST ($(du -sh "$DEST" | awk '{print $1}'))"
echo "Review and commit when ready."
