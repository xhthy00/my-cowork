#!/usr/bin/env bash
# Build macOS backend binary and smoke-start it.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"

sqlite_ext_ok() {
  uv run python -c "import sqlite3; sqlite3.connect(':memory:').enable_load_extension(True)" 2>/dev/null
}

uv sync
if ! sqlite_ext_ok; then
  echo "sqlite3 cannot load extensions; switching to Homebrew CPython"
  if brew install python@3.12; then
    uv sync --python "$(brew --prefix python@3.12)/bin/python3.12" || true
  fi
fi
if sqlite_ext_ok; then
  echo "sqlite3.enable_load_extension: OK"
else
  echo "WARNING: sqlite-vec extensions unavailable; LongTermStore will degrade"
fi

uv run pyinstaller "$ROOT/build/pyinstaller/macos.spec" --distpath "$ROOT/dist" --workpath "$ROOT/build/pyinstaller/work-macos" -y
BIN="$ROOT/dist/my-cowork-backend"
if [[ ! -f "$BIN" ]]; then
  echo "binary missing: $BIN" >&2
  ls -la "$ROOT/dist" || true
  exit 1
fi
chmod +x "$BIN"
ls -lh "$BIN"

mkdir -p "$ROOT/build/pyinstaller"
LOG="$ROOT/build/pyinstaller/smoke-macos.log"
export MY_COWORK_API_KEY="${MY_COWORK_API_KEY:-smoke-test-key}"
export MY_COWORK_PROVIDER="${MY_COWORK_PROVIDER:-openai_compat}"
export MY_COWORK_MODEL="${MY_COWORK_MODEL:-gpt-4o-mini}"
export MY_COWORK_ENABLE_SCHEDULER=0
export MY_COWORK_CHANNEL_AUTOSTART=0
export PYTHONUNBUFFERED=1
export PYTHONFAULTHANDLER=1
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

# One-file PyInstaller first boot extracts then create_app() compiles graphs.
"$BIN" --port 8765 >"$LOG" 2>&1 &
PID=$!
cleanup() { kill "$PID" 2>/dev/null || true; wait "$PID" 2>/dev/null || true; }
trap cleanup EXIT

ok=0
for _ in $(seq 1 180); do
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "backend exited before becoming healthy, pid=$PID"
    wait "$PID" || true
    break
  fi
  if curl -sf --max-time 2 "http://127.0.0.1:8765/health" >/dev/null; then
    ok=1
    break
  fi
  sleep 1
done

if [[ "$ok" -eq 1 ]]; then
  echo "SMOKE OK"
  exit 0
fi
echo "SMOKE FAIL — log:"
cat "$LOG" || true
exit 1
