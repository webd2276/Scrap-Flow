#!/usr/bin/env bash
# macOS entry point for the ScrapeFlow Strix security scan.
#
# This wrapper adds macOS-specific prerequisite checks and then delegates to
# scripts/security-scan.sh, so Linux and macOS share one implementation and
# cannot drift.
#
# Usage:
#   ./scripts/security-scan-macos.sh
#   ./scripts/security-scan-macos.sh live
#   ./scripts/security-scan-macos.sh --help
#
# Environment: same as scripts/security-scan.sh (STRIX_LLM, LLM_API_KEY,
# SF_STRIX_MODE, SF_STRIX_BUDGET, SF_STRIX_KEEP, STRIX_TEST_EMAIL,
# STRIX_TEST_PASSWORD).
set -euo pipefail

SELF_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [ "$(uname -s)" != "Darwin" ]; then
  printf 'warning: security-scan-macos.sh targets macOS; delegating to scripts/security-scan.sh anyway\n' >&2
fi

if ! command -v bash >/dev/null 2>&1; then
  printf 'error: bash is required (macOS ships /bin/bash)\n' >&2
  exit 1
fi

# Docker Desktop installs its CLI here. Homebrew and manual installs may put it
# elsewhere, so only add the standard path when the executable exists.
if [ -x /Applications/Docker.app/Contents/Resources/bin/docker ]; then
  PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
  export PATH
fi

if ! command -v docker >/dev/null 2>&1; then
  printf 'error: docker is not installed or not on PATH\n' >&2
  printf 'Install Docker Desktop for Mac: https://docs.docker.com/desktop/setup/install/mac-install/\n' >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  printf 'error: the Docker daemon is not running\n' >&2
  printf 'Start Docker Desktop for Mac and wait for the whale icon to settle.\n' >&2
  exit 1
fi

if ! command -v strix >/dev/null 2>&1; then
  printf 'error: strix is not installed or not on PATH\n' >&2
  printf 'Install it with: uv tool install strix-agent==1.7.0\n' >&2
  printf 'Strix also needs an LLM key: export STRIX_LLM=... LLM_API_KEY=...\n' >&2
  exit 1
fi

exec bash "$SELF_DIR/security-scan.sh" "$@"
