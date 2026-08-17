#!/usr/bin/env bash
# Build macOS backend binary and smoke-start it.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
uv sync
uv run pyinstaller "$ROOT/build/pyinstaller/macos.spec" --distpath "$ROOT/dist" --workpath "$ROOT/build/pyinstaller/work-macos" -y
BIN="$ROOT/dist/my-cowork-backend"
export MY_COWORK_API_KEY="${MY_COWORK_API_KEY:-smoke-test-key}"
export MY_COWORK_PROVIDER="${MY_COWORK_PROVIDER:-openai_compat}"
export MY_COWORK_MODEL="${MY_COWORK_MODEL:-gpt-4o-mini}"
export MY_COWORK_ENABLE_SCHEDULER=0
# Smoke: start briefly and look for listen line
timeout 20s "$BIN" --port 8765 >"$ROOT/build/pyinstaller/smoke-macos.log" 2>&1 &
PID=$!
sleep 3
if grep -E "Uvicorn running|127\\.0\\.0\\.1:" "$ROOT/build/pyinstaller/smoke-macos.log"; then
  echo "SMOKE OK"
  kill "$PID" 2>/dev/null || true
  exit 0
fi
echo "SMOKE FAIL — log:"
cat "$ROOT/build/pyinstaller/smoke-macos.log" || true
kill "$PID" 2>/dev/null || true
exit 1
