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
export PYTHONUNBUFFERED=1
# Smoke: start briefly and look for listen line.
# Stock macOS has no GNU timeout(1); background + kill is enough.
"$BIN" --port 8765 >"$ROOT/build/pyinstaller/smoke-macos.log" 2>&1 &
PID=$!
cleanup() { kill "$PID" 2>/dev/null || true; wait "$PID" 2>/dev/null || true; }
trap cleanup EXIT
sleep 5
if grep -E "Uvicorn running|127\\.0\\.0\\.1:" "$ROOT/build/pyinstaller/smoke-macos.log"; then
  echo "SMOKE OK"
  exit 0
fi
echo "SMOKE FAIL — log:"
cat "$ROOT/build/pyinstaller/smoke-macos.log" || true
exit 1
