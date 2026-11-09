#!/usr/bin/env bash
# macOS entry point for the ScrapeFlow runner.
#
# This wrapper adds macOS-specific prerequisite checks and then delegates to
# scripts/run.sh, so Linux and macOS share one implementation and cannot drift.
#
# Usage:
#   ./scripts/run-macos.sh
#   ./scripts/run-macos.sh logs
#   ./scripts/run-macos.sh fix-db-password
#
# Environment: same as scripts/run.sh (SF_S3_MODE, SF_ENV_FILE,
# SF_HEALTH_TIMEOUT, MINIO_IMAGE).
set -euo pipefail

SELF_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SELF_DIR/.." && pwd)"

if [ "$(uname -s)" != "Darwin" ]; then
  printf 'warning: run-macos.sh targets macOS; delegating to scripts/run.sh anyway\n' >&2
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

if [ ! -f "${SF_ENV_FILE:-$ROOT/.env}" ] && ! command -v python3 >/dev/null 2>&1; then
  printf 'error: python3 is required to generate .env on macOS\n' >&2
  printf 'Install it with: xcode-select --install   (or: brew install python)\n' >&2
  exit 1
fi

exec bash "$SELF_DIR/run.sh" "$@"
