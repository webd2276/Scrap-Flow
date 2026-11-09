#!/usr/bin/env bash
# Start (or control) the complete ScrapeFlow stack with one command.
#
# Usage:
#   ./scripts/run.sh            # build + start everything, wait for readiness
#   ./scripts/run.sh logs       # follow API/worker/beat/web logs
#   ./scripts/run.sh status     # container status
#   ./scripts/run.sh seed       # create demo org/user/API key (prints once)
#   ./scripts/run.sh stop       # stop containers, keep data volumes
#   ./scripts/run.sh reset      # stop containers and delete data volumes
#
# Environment:
#   SF_S3_MODE=auto|minio|s3mock  (default: auto)
#   SF_ENV_FILE=/path/.env        (default: <repo>/.env)
#   SF_HEALTH_TIMEOUT=240         seconds to wait for /ready
#   MINIO_IMAGE=...               image tried when SF_S3_MODE=auto|minio
set -euo pipefail

SELF="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/$(basename -- "${BASH_SOURCE[0]}")"
ROOT="$(cd -- "$(dirname -- "$SELF")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${SF_ENV_FILE:-$ROOT/.env}"
S3_MODE="${SF_S3_MODE:-auto}"
HEALTH_TIMEOUT="${SF_HEALTH_TIMEOUT:-240}"
MINIO_IMAGE="${MINIO_IMAGE:-quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z}"

RUN_DIR="$ROOT/.run"
S3MOCK_OVERRIDE="$RUN_DIR/s3mock-override.yml"
EXTRA_FILES=()

log() { printf '\n==> %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '2,20p' "$SELF" | sed 's/^# \{0,1\}//'
}

compose() {
  docker compose \
    --project-directory "$ROOT" \
    -f "$ROOT/docker-compose.yml" \
    "${EXTRA_FILES[@]}" \
    --env-file "$ENV_FILE" \
    "$@"
}

write_s3mock_override() {
  mkdir -p "$RUN_DIR"
  cat >"$S3MOCK_OVERRIDE" <<'YAML'
services:
  minio:
    image: adobe/s3mock:latest
    command: []
    environment:
      HTTP_PORT: "9000"
      COM_ADOBE_TESTING_S3MOCK_STORE_INITIAL_BUCKETS: scrapeflow
    healthcheck:
      test: ["CMD-SHELL", "exit 0"]
      interval: 2s
      timeout: 2s
      retries: 5
    ports:
      - "127.0.0.1:9000:9000"

  minio-init:
    command: ["python", "-c", "print('S3 mock bucket pre-created')"]
YAML
}

select_s3() {
  case "$S3_MODE" in
    minio)
      log "Using MinIO image: $MINIO_IMAGE"
      ;;
    s3mock)
      log "Using adobe/s3mock for S3"
      write_s3mock_override
      EXTRA_FILES+=(-f "$S3MOCK_OVERRIDE")
      ;;
    auto)
      if docker image inspect "$MINIO_IMAGE" >/dev/null 2>&1; then
        log "Using local MinIO image: $MINIO_IMAGE"
      elif command -v timeout >/dev/null 2>&1 \
        && timeout 120 docker pull "$MINIO_IMAGE" >/dev/null 2>&1; then
        log "Pulled MinIO image: $MINIO_IMAGE"
      else
        warn "MinIO image is unavailable; falling back to adobe/s3mock."
        warn "Set SF_S3_MODE=minio to require real MinIO instead."
        write_s3mock_override
        EXTRA_FILES+=(-f "$S3MOCK_OVERRIDE")
      fi
      ;;
    *)
      die "SF_S3_MODE must be auto, minio, or s3mock (got: $S3_MODE)"
      ;;
  esac
}

require_prerequisites() {
  command -v docker >/dev/null 2>&1 || die "docker is not installed"
  docker info >/dev/null 2>&1 || die "the Docker daemon is not running"
  docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required"
  command -v curl >/dev/null 2>&1 || die "curl is required"

  if [ ! -f "$ENV_FILE" ]; then
    log "Creating $ENV_FILE with random secrets"
    command -v python3 >/dev/null 2>&1 || die "python3 is required to generate .env"
    python3 "$ROOT/scripts/generate_env.py"
  fi
  [ -f "$ENV_FILE" ] || die "missing environment file: $ENV_FILE"
}

wait_for_api() {
  log "Waiting up to ${HEALTH_TIMEOUT}s for the API"
  local deadline=$((SECONDS + HEALTH_TIMEOUT))
  while ((SECONDS < deadline)); do
    if curl -fsS http://127.0.0.1:8000/ready >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done

  compose ps || true
  compose logs --tail=80 api migrate worker >&2 || true
  die "API did not become ready within ${HEALTH_TIMEOUT}s"
}

wait_for_web() {
  local deadline=$((SECONDS + 90))
  while ((SECONDS < deadline)); do
    if curl -fsS http://127.0.0.1:3000/login >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  warn "dashboard is not answering on http://127.0.0.1:3000 yet"
}

start() {
  require_prerequisites
  select_s3

  log "Building and starting ScrapeFlow (first run can take several minutes)"
  compose up -d --build

  wait_for_api
  wait_for_web

  compose ps

  cat <<EOF

ScrapeFlow is running.

  API         http://127.0.0.1:8000
  API docs    http://127.0.0.1:8000/docs
  Dashboard   http://127.0.0.1:3000
  Metrics     http://127.0.0.1:8000/metrics

Useful commands:
  ./scripts/run.sh logs      follow logs
  ./scripts/run.sh seed      create demo user + API key
  ./scripts/run.sh stop      stop containers (data is kept)
  ./scripts/run.sh reset     stop and delete data volumes

S3 mode: ${S3_MODE}
EOF
}

case "${1:-start}" in
  start)
    start
    ;;
  logs)
    [ -f "$ENV_FILE" ] || die "missing environment file: $ENV_FILE"
    compose logs -f --tail=100 api worker beat web egress-proxy
    ;;
  status | ps)
    [ -f "$ENV_FILE" ] || die "missing environment file: $ENV_FILE"
    compose ps
    ;;
  seed)
    [ -f "$ENV_FILE" ] || die "missing environment file: $ENV_FILE"
    compose exec api python -m scripts.seed
    ;;
  stop)
    [ -f "$ENV_FILE" ] || die "missing environment file: $ENV_FILE"
    compose down
    ;;
  reset)
    [ -f "$ENV_FILE" ] || die "missing environment file: $ENV_FILE"
    log "Stopping containers and deleting data volumes"
    compose down -v
    ;;
  -h | --help | help)
    usage
    ;;
  *)
    usage
    die "unknown command: $1"
    ;;
esac
