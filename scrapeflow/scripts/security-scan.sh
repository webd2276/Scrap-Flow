#!/usr/bin/env bash
# Run a Strix pentest against ScrapeFlow.
#
# Usage:
#   ./scripts/security-scan.sh              # scan the committed source tree
#   ./scripts/security-scan.sh code         # same as above
#   ./scripts/security-scan.sh live         # scan the running API on :8000
#   ./scripts/security-scan.sh --help
#
# Requirements:
#   - Docker running (Strix spawns a sandbox container)
#   - strix on PATH            (uv tool install strix-agent==1.7.0)
#   - STRIX_LLM and LLM_API_KEY exported
#
# Environment:
#   SF_STRIX_MODE=quick|standard|deep   (default: quick)
#   SF_STRIX_BUDGET=10                  LLM spend cap in USD
#   SF_STRIX_KEEP=1                     keep the throwaway worktree
#   STRIX_TEST_EMAIL / STRIX_TEST_PASSWORD
#                                       optional credentials for live testing
#
# The code scan runs against a detached git worktree: Strix mounts a local
# target read-write by default, and we do not want the agent editing the files
# you are working on.
set -euo pipefail

SELF="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/$(basename -- "${BASH_SOURCE[0]}")"
ROOT="$(cd -- "$(dirname -- "$SELF")/.." && pwd)"
cd "$ROOT"

RUN_DIR="$ROOT/.run"
WORKTREE="$RUN_DIR/strix-worktree"
LOG_DIR="$ROOT/strix_runs"
MODE="${1:-code}"
SCAN_MODE="${SF_STRIX_MODE:-quick}"
BUDGET="${SF_STRIX_BUDGET:-10}"

log() { printf '\n==> %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Run a Strix pentest against ScrapeFlow.

Usage:
  ./scripts/security-scan.sh              scan the committed source tree
  ./scripts/security-scan.sh code         same as above
  ./scripts/security-scan.sh live         scan the running API on :8000
  ./scripts/security-scan.sh --help       show this help

Requirements:
  Docker running, strix on PATH, STRIX_LLM and LLM_API_KEY exported.

Environment:
  SF_STRIX_MODE=quick|standard|deep       scan depth (default: quick)
  SF_STRIX_BUDGET=10                      LLM spend cap in USD
  SF_STRIX_KEEP=1                         keep the throwaway worktree
  STRIX_TEST_EMAIL, STRIX_TEST_PASSWORD   optional live-test credentials

Results are written to strix_runs/. Open them with: strix view
EOF
}

case "$MODE" in
  code|live) ;;
  -h|--help|help) usage; exit 0 ;;
  *) die "unknown mode '$MODE' (expected 'code' or 'live')" ;;
esac

log "Checking prerequisites"
command -v docker >/dev/null || die "docker not found"
docker info >/dev/null 2>&1 || die "docker daemon is not running"
command -v strix >/dev/null || die "strix not found: uv tool install strix-agent==1.7.0"
[ -n "${STRIX_LLM:-}" ] || die "STRIX_LLM is not set (for example openrouter/z-ai/glm-5.3)"
[ -n "${LLM_API_KEY:-}" ] || die "LLM_API_KEY is not set"

case "$SCAN_MODE" in
  quick|standard|deep) ;;
  *) die "SF_STRIX_MODE must be quick, standard or deep (got '$SCAN_MODE')" ;;
esac
case "$BUDGET" in
  ''|*[!0-9.]*) die "SF_STRIX_BUDGET must be a number (got '$BUDGET')" ;;
esac

cmd=(strix -n)

if [ "$MODE" = "live" ]; then
  log "Checking the local stack"
  curl -fsS -o /dev/null http://127.0.0.1:8000/ready \
    || die "API is not ready on :8000; start it with ./scripts/run.sh"

  mkdir -p "$RUN_DIR"
  curl -fsS http://127.0.0.1:8000/openapi.json -o "$RUN_DIR/strix-openapi.json" \
    || die "could not download /openapi.json"

  # The spec drives coverage; the base URL gives the agent a host to attack.
  cmd+=(--target "$RUN_DIR/strix-openapi.json" --target "http://127.0.0.1:8000")

  if [ -n "${STRIX_TEST_EMAIL:-}" ] && [ -n "${STRIX_TEST_PASSWORD:-}" ]; then
    cmd+=(--instruction "Grey-box testing. Sign in with POST /v1/auth/login using
      email ${STRIX_TEST_EMAIL} and password ${STRIX_TEST_PASSWORD}, then use the
      returned bearer token for the authenticated endpoints. Stay inside
      localhost and do not attack external hosts.")
  else
    cmd+=(--instruction "Stay inside localhost and do not attack external hosts.
      Register a disposable account through /v1/auth/signup to reach
      authenticated endpoints.")
  fi
else
  log "Preparing an isolated worktree at HEAD"
  if [ -d "$WORKTREE" ]; then
    git -C "$ROOT" worktree remove --force "$WORKTREE" >/dev/null 2>&1 || rm -rf "$WORKTREE"
  fi
  git -C "$ROOT" worktree prune
  rm -rf "$WORKTREE"
  git -C "$ROOT" worktree add --detach "$WORKTREE" HEAD >/dev/null

  if ! git -C "$ROOT" diff --quiet || ! git -C "$ROOT" diff --cached --quiet; then
    warn "uncommitted changes are not part of the scan; the worktree is at HEAD"
  fi

  cmd+=(--target "$WORKTREE")
fi

cleanup() {
  if [ "$MODE" = "code" ] && [ "${SF_STRIX_KEEP:-0}" != "1" ]; then
    git -C "$ROOT" worktree remove --force "$WORKTREE" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

log "Running Strix ($MODE · $SCAN_MODE · budget \$$BUDGET)"
set +e
"${cmd[@]}" \
  --scan-mode "$SCAN_MODE" \
  --scope-mode full \
  --max-budget "$BUDGET" \
  --max-turns 300
code=$?
set -e

if [ "$code" -eq 1 ]; then
  die "Strix failed before finishing; see the log above"
fi

log "Done (exit $code)"
printf 'Reports: %s\n' "$LOG_DIR"
if [ "$MODE" = "code" ] && [ "${SF_STRIX_KEEP:-0}" = "1" ]; then
  printf 'Worktree kept for review: %s\n' "$WORKTREE"
fi
printf 'Open the dashboard with: strix view\n'
if [ "$code" -eq 2 ]; then
  printf '\nFindings were reported. Triage them before treating any of them as real.\n'
fi
exit "$code"
