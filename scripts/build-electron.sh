#!/usr/bin/env bash
# Build renderer+main and package with electron-builder.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
bash scripts/fetch-officecli.sh
npm run prebuild:terminal-deps
npm run build
# electron-builder expects main at dist-electron/; tsc already emits there.
npx electron-builder --config build/electron-builder.yml "$@"
