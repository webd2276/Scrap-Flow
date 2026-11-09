#!/usr/bin/env bash
# Start (or control) the complete ScrapeFlow stack with one command.
#
# Usage:
#   ./scripts/run.sh            # build + start everything, wait for readiness
#   ./scripts/run.sh logs       # follow API/worker/beat/web logs
#   ./scripts/run.sh status     # container status
#   ./scripts/run.sh seed       # create demo org/user/API key (prints once)
#   ./scripts/run.sh fix-db-password  # sync the Postgres role to .env, keep data
#   ./scripts/run.sh stop       # stop containers, keep data volumes
#   ./scripts/run.sh reset      # stop containers and delete data volumes
#
# Environment:
#   SF_S3_MODE=auto|minio|s3mock  (default: auto)
#   SF_ENV_FILE=/path/.env        (default: <repo>/.env)
#   SF_HEALTH_TIMEOUT=240         seconds to wait for /ready
#   MINIO_IMAGE=...               image tried when SF_S3_MODE=auto|minio
#
# Platform: Linux and macOS. The macOS entry point is scripts/run-macos.sh,
# which performs macOS-specific checks and delegates to this shared runner.
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
EFFECTIVE_S3_MODE="$S3_MODE"

log() { printf '\n==> %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

env_value() {
  local key="$1"
  python3 - "$ENV_FILE" "$key" <<'PY'
import sys
from pathlib import Path

path, key = sys.argv[1], sys.argv[2]
for line in Path(path).read_text().splitlines():
    stripped = line.strip()
    if stripped.startswith("#") or "=" not in stripped:
        continue
    name, value = stripped.split("=", 1)
    if name.strip() == key:
        print(value.strip())
        break
PY
}

usage() {
  cat <<'EOF'
Start (or control) the complete ScrapeFlow stack with one command.

Usage:
  ./scripts/run.sh                   build + start, wait for readiness
  ./scripts/run.sh logs              follow API/worker/beat/web logs
  ./scripts/run.sh status            container status
  ./scripts/run.sh seed              create demo org/user/API key (prints once)
  ./scripts/run.sh fix-db-password   sync the Postgres role to .env, keep data
  ./scripts/run.sh stop              stop containers, keep data volumes
  ./scripts/run.sh reset             stop containers and delete data volumes

Environment:
  SF_S3_MODE=auto|minio|s3mock       default: auto
  SF_ENV_FILE=/path/.env             default: <repo>/.env
  SF_HEALTH_TIMEOUT=240              seconds to wait for /ready
  MINIO_IMAGE=...                    image tried in auto/minio mode
EOF
}

compose() {
  # Build the argument list explicitly. macOS ships Bash 3.2, where expanding
  # an empty array under `set -u` can raise "unbound variable".
  local args
  args=(docker compose --project-directory "$ROOT" -f "$ROOT/docker-compose.yml")
  if [ "${#EXTRA_FILES[@]}" -gt 0 ]; then
    args+=("${EXTRA_FILES[@]}")
  fi
  args+=(--env-file "$ENV_FILE")
  "${args[@]}" "$@"
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

pull_minio_image() {
  # GNU coreutils provides timeout on Linux; macOS usually has neither timeout
  # nor gtimeout. Fall back to a portable watchdog so a slow registry cannot
  # block the runner forever.
  if command -v timeout >/dev/null 2>&1; then
    timeout 120 docker pull "$MINIO_IMAGE" >/dev/null 2>&1
    return $?
  fi
  if command -v gtimeout >/dev/null 2>&1; then
    gtimeout 120 docker pull "$MINIO_IMAGE" >/dev/null 2>&1
    return $?
  fi

  docker pull "$MINIO_IMAGE" >/dev/null 2>&1 &
  local pid=$!
  local waited=0
  while kill -0 "$pid" 2>/dev/null; do
    if [ "$waited" -ge 120 ]; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
      return 124
    fi
    sleep 1
    waited=$((waited + 1))
  done
  wait "$pid"
}

select_s3() {
  case "$S3_MODE" in
    minio)
      EFFECTIVE_S3_MODE="minio"
      log "Using MinIO image: $MINIO_IMAGE"
      ;;
    s3mock)
      EFFECTIVE_S3_MODE="s3mock"
      log "Using adobe/s3mock for S3"
      write_s3mock_override
      EXTRA_FILES+=(-f "$S3MOCK_OVERRIDE")
      ;;
    auto)
      if docker image inspect "$MINIO_IMAGE" >/dev/null 2>&1; then
        EFFECTIVE_S3_MODE="minio"
        log "Using local MinIO image: $MINIO_IMAGE"
      elif pull_minio_image; then
        EFFECTIVE_S3_MODE="minio"
        log "Pulled MinIO image: $MINIO_IMAGE"
      else
        EFFECTIVE_S3_MODE="s3mock"
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
    command -v python3 >/dev/null 2>&1 \
      || die "python3 is required to generate .env (macOS: run 'xcode-select --install' or 'brew install python')"
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
  if ! compose up -d --build; then
    compose logs --tail=40 migrate >&2 || true
    cat >&2 <<'EOF'

Startup failed. If migrate reports "password authentication failed", the
PostgreSQL data volume was created with a different password than the current
.env. Repair it without deleting data:

  ./scripts/run.sh fix-db-password

Or delete local data and start clean:

  ./scripts/run.sh reset
EOF
    exit 1
  fi

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

S3 mode: ${EFFECTIVE_S3_MODE}
EOF
}

fix_db_password() {
  require_prerequisites
  command -v python3 >/dev/null 2>&1 \
    || die "python3 is required to repair the database password (macOS: run 'xcode-select --install' or 'brew install python')"

  local user
  user="$(env_value POSTGRES_USER)"
  user="${user:-scrapeflow}"

  log "Starting PostgreSQL"
  compose up -d postgres

  local deadline=$((SECONDS + 90))
  until compose exec -T postgres pg_isready -U "$user" -d postgres >/dev/null 2>&1; do
    ((SECONDS < deadline)) || die "PostgreSQL did not become ready"
    sleep 2
  done

  mkdir -p "$RUN_DIR"
  local sql_file="$RUN_DIR/fix-db-password.sql"
  (
    umask 077
    python3 - "$ENV_FILE" >"$sql_file" <<'PY'
import re
import sys
import urllib.parse
from pathlib import Path

env: dict[str, str] = {}
for line in Path(sys.argv[1]).read_text().splitlines():
    stripped = line.strip()
    if stripped.startswith("#") or "=" not in stripped:
        continue
    name, value = stripped.split("=", 1)
    env[name.strip()] = value.strip()

url = env.get("DATABASE_URL", "")
match = re.match(r"^[^:]+://([^:]+):([^@]*)@", url)
if not match:
    raise SystemExit("DATABASE_URL is missing a user/password")

user = urllib.parse.unquote(match.group(1))
password = urllib.parse.unquote(match.group(2))
role = user.replace('"', '""')
literal = password.replace("'", "''")
print(f'ALTER ROLE "{role}" WITH PASSWORD \'{literal}\';')
print(f"\\echo role {user} now matches DATABASE_URL")
PY
  ) || {
    rm -f "$sql_file"
    die "could not read DATABASE_URL from $ENV_FILE"
  }

  compose exec -T postgres psql -U "$user" -d postgres -v ON_ERROR_STOP=1 <"$sql_file"
  rm -f "$sql_file"
  log "Postgres role password now matches DATABASE_URL"
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
  fix-db-password)
    fix_db_password
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
