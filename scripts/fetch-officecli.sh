#!/usr/bin/env bash
# Download OfficeCLI binary for the current (or forced) platform into resources/bin/.
# Mirrors the official install.sh strategy: d.officecli.ai first, GitHub fallback.
# Usage:
#   bash scripts/fetch-officecli.sh
#   OFFICECLI_PLATFORM=mac-arm64 bash scripts/fetch-officecli.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$ROOT/resources/bin"
mkdir -p "$OUT_DIR"

MIRROR_BASE="https://d.officecli.ai"
GITHUB_LATEST="https://github.com/iOfficeAI/OfficeCLI/releases/latest/download"

detect_platform() {
  local os arch
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  arch="$(uname -m)"
  case "$os" in
    darwin)
      case "$arch" in
        arm64|aarch64) echo "mac-arm64" ;;
        *) echo "mac-x64" ;;
      esac
      ;;
    linux)
      case "$arch" in
        arm64|aarch64) echo "linux-arm64" ;;
        *) echo "linux-x64" ;;
      esac
      ;;
    mingw*|msys*|cygwin*)
      case "$arch" in
        arm64|aarch64) echo "win-arm64" ;;
        *) echo "win-x64" ;;
      esac
      ;;
    *)
      echo "unsupported OS: $os" >&2
      exit 1
      ;;
  esac
}

PLATFORM="${OFFICECLI_PLATFORM:-$(detect_platform)}"
case "$PLATFORM" in
  mac-arm64) ASSET="officecli-mac-arm64"; DEST="officecli" ;;
  mac-x64) ASSET="officecli-mac-x64"; DEST="officecli" ;;
  linux-arm64) ASSET="officecli-linux-arm64"; DEST="officecli" ;;
  linux-x64) ASSET="officecli-linux-x64"; DEST="officecli" ;;
  win-arm64) ASSET="officecli-win-arm64.exe"; DEST="officecli.exe" ;;
  win-x64) ASSET="officecli-win-x64.exe"; DEST="officecli.exe" ;;
  *)
    echo "unknown OFFICECLI_PLATFORM=$PLATFORM" >&2
    exit 1
    ;;
esac

DEST_PATH="$OUT_DIR/$DEST"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

resolve_version() {
  local url
  url="$(curl -fsSL --max-time 30 --connect-timeout 5 -o /dev/null -w '%{url_effective}' \
    "$MIRROR_BASE/releases/latest" 2>/dev/null || true)"
  case "$url" in
    */releases/tag/v*) echo "${url##*/tag/}"; return 0 ;;
  esac
  url="$(curl -fsSL --max-time 30 -o /dev/null -w '%{url_effective}' \
    "https://github.com/iOfficeAI/OfficeCLI/releases/latest" 2>/dev/null || true)"
  case "$url" in
    */releases/tag/v*) echo "${url##*/tag/}"; return 0 ;;
  esac
  return 1
}

fetch_with_fallback() {
  local primary="$1" fallback="$2"
  if curl -fsSL --max-time 300 --connect-timeout 5 "$primary" -o "$TMP"; then
    echo "  (via primary)"
    return 0
  fi
  echo "  primary failed, trying fallback..."
  curl -fsSL --max-time 300 "$fallback" -o "$TMP"
}

VERSION="${OFFICECLI_VERSION:-}"
if [[ -z "$VERSION" ]]; then
  VERSION="$(resolve_version || true)"
fi

echo "Fetching OfficeCLI ${VERSION:-latest} (${PLATFORM}) → ${DEST_PATH}"

OK=0
if [[ -n "$VERSION" ]]; then
  if fetch_with_fallback \
    "$MIRROR_BASE/releases/download/${VERSION}/${ASSET}" \
    "https://github.com/iOfficeAI/OfficeCLI/releases/download/${VERSION}/${ASSET}"; then
    OK=1
  fi
fi
if [[ "$OK" -eq 0 ]]; then
  if fetch_with_fallback \
    "$MIRROR_BASE/releases/latest/download/${ASSET}" \
    "$GITHUB_LATEST/${ASSET}"; then
    OK=1
  fi
fi
if [[ "$OK" -eq 0 && -x "${HOME}/.local/bin/officecli" && "$DEST" == "officecli" ]]; then
  echo "Falling back to ~/.local/bin/officecli"
  cp "${HOME}/.local/bin/officecli" "$TMP"
  OK=1
fi
if [[ "$OK" -eq 0 ]]; then
  echo "Failed to download OfficeCLI asset ${ASSET}" >&2
  exit 1
fi

chmod +x "$TMP"
# Drop macOS quarantine so Electron/Python can exec the binary.
if command -v xattr >/dev/null 2>&1; then
  xattr -cr "$TMP" 2>/dev/null || true
fi
mv "$TMP" "$DEST_PATH"
trap - EXIT

"$DEST_PATH" --version
echo "OK: $DEST_PATH"
