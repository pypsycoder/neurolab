#!/usr/bin/env bash
# No secrets or agent execution. Restore pinned official ARM64 code-agent assets.
set -euo pipefail
[[ "$(uname -m)" == aarch64 ]] || { echo 'This installer is ARM64-only'; exit 2; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
OUT="$ROOT/runtime/openhands-eval/bin"
mkdir -p "$OUT"
CLI="$OUT/openhands-1.16.0-linux-arm64"
EXPECTED=67c5cfb94e5fd4c4120eb0360b0f23337da31f64a70e8496bcf008e4caeea6af
if [[ ! -f "$CLI" ]]; then
  curl --fail --silent --show-error --location --proto '=https' --max-time 180 \
    https://github.com/OpenHands/OpenHands-CLI/releases/download/1.16.0/openhands-linux-arm64 \
    --output "$CLI.download"
  printf '%s  %s\n' "$EXPECTED" "$CLI.download" | sha256sum -c -
  mv -- "$CLI.download" "$CLI"
fi
printf '%s  %s\n' "$EXPECTED" "$CLI" | sha256sum -c -
chmod 755 "$CLI"
cd "$ROOT"
docker build -f research/gpt2giga.Dockerfile -t neurolab/gpt2giga-eval:v0.3.0 .
echo 'engineering_runtime: pinned CLI checksum and gateway image verified; no agent run'
