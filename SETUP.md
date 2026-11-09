# ScrapeFlow — Complete Setup Guide

This guide takes you from a fresh clone to a running multi-tenant scraping
platform, then shows how to test it, configure proxies and billing, deploy it
to a server, and publish the repository to GitHub.

ScrapeFlow is a FastAPI + Celery + Selenium Grid API with a Next.js dashboard.
The API accepts jobs, workers execute them in Chrome or plain HTTP behind a
validating egress proxy, and results/artifacts are stored in S3-compatible
storage.

```
Browser / curl
      │
      ▼
FastAPI (apps/api) ──► Redis + Celery ──► Worker (apps/worker)
      │                                      │
      ▼                                      ├─► Selenium Grid (Chrome)
PostgreSQL (jobs, tenants, billing)          ├─► egress proxy (SSRF checks)
      ▲                                      └─► S3/MinIO (artifacts)
      │
Celery Beat (schedules, reaper, webhooks, retention)
Next.js dashboard (apps/web) ── same-origin BFF ──► FastAPI
```

> Repository layout: the Git repository root contains `scrapeflow/`, `docs/`,
> `SETUP.md`, and `.github/`. Run application commands from `scrapeflow/` unless
> a step says otherwise.

---

## 1. Prerequisites

### Required for the Docker setup

| Tool | Linux | macOS | Windows |
|---|---|---|---|
| Docker Engine 24+ | required | Docker Desktop | Docker Desktop |
| Docker Compose v2 | required | included | included |
| Git | required | required | required |
| Bash 3.2+ | required by `run.sh` | built in | not needed for `run.ps1` |
| PowerShell 5.1+ | optional | optional | required for `run.ps1` |
| curl | required by `run.sh` | required by `run.sh` | not needed by `run.ps1` |
| jq | optional (API examples) | optional | optional |
| Disk space | ~10 GB free | ~10 GB free | ~10 GB free |
| RAM | 8 GB recommended | 8 GB recommended | 8 GB recommended |

### Required only for local development or tests

| Tool | Version | Check |
|---|---|---|
| Python | 3.12 | `python3 --version` |
| uv | 0.13+ | `uv --version` |
| Node.js | 22+ | `node --version` |
| npm | 10+ | `npm --version` |

Platform notes:

- **Windows native:** use `scripts\run.ps1` or `scripts\run.cmd`. It needs
  Docker Desktop and PowerShell only; it generates `.env` itself and does not
  require Bash, Python, or curl.
- **Windows WSL 2 / Git Bash:** use `./scripts/run.sh`. WSL needs Docker
  integration enabled in Docker Desktop.
- **macOS:** use `./scripts/run-macos.sh`, which delegates to the shared
  `run.sh`. `python3` is only needed to create `.env` or run
  `fix-db-password`; install it with `xcode-select --install` or
  `brew install python`.

---

## 2. Get the project

```bash
git clone <YOUR_REPOSITORY_URL> web-scrapping-tool
cd web-scrapping-tool/scrapeflow
```

If you already have the repository on disk, just `cd` into `scrapeflow/`
(Windows: `cd web-scrapping-tool\scrapeflow`).

All remaining commands assume you are inside the `scrapeflow/` directory:

```bash
pwd   # .../web-scrapping-tool/scrapeflow
```

---

## 3. Fastest start — one command

The included runners build the images, create `.env` with random secrets if it
is missing, start every service, and wait until the API and dashboard answer.
All three platforms share the same Compose files and the same commands.

| Platform | Start command |
|---|---|
| Linux | `./scripts/run.sh` |
| macOS | `./scripts/run-macos.sh` |
| Windows PowerShell | `powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1` |
| Windows CMD | `scripts\run.cmd` |

What they do:

1. Check Docker and Compose v2 (and curl on Linux/macOS).
2. Create `.env` with random secrets when missing.
3. Try the pinned MinIO image. If it cannot be pulled, fall back to the
   `adobe/s3mock` container so the stack still works locally.
4. Build and start `postgres`, `redis`, `minio`, `migrate`, `minio-init`,
   `api`, `worker`, `beat`, `egress-proxy`, `selenium`, and `web`.
5. Wait for `http://127.0.0.1:8000/ready`.
6. Print the URLs.

Runner commands:

| Action | Linux / macOS | Windows PowerShell |
|---|---|---|
| Start or update | `./scripts/run.sh` | `.\scripts\run.ps1` |
| Container status | `./scripts/run.sh status` | `.\scripts\run.ps1 status` |
| Follow logs | `./scripts/run.sh logs` | `.\scripts\run.ps1 logs` |
| Seed demo data | `./scripts/run.sh seed` | `.\scripts\run.ps1 seed` |
| Repair DB password | `./scripts/run.sh fix-db-password` | `.\scripts\run.ps1 fix-db-password` |
| Stop (keep data) | `./scripts/run.sh stop` | `.\scripts\run.ps1 stop` |
| Stop and delete data | `./scripts/run.sh reset` | `.\scripts\run.ps1 reset` |

If PowerShell's execution policy blocks the script, use the launcher or pass
`-ExecutionPolicy Bypass`:

```powershell
scripts\run.cmd
# or
powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

Force a storage mode if the automatic choice is not what you want:

```bash
# Linux / macOS
SF_S3_MODE=s3mock ./scripts/run.sh   # always use the S3 mock
SF_S3_MODE=minio  ./scripts/run.sh   # require real MinIO
```

```powershell
# Windows PowerShell
$env:SF_S3_MODE = 's3mock'; .\scripts\run.ps1
$env:SF_S3_MODE = 'minio';  .\scripts\run.ps1
```

```bat
rem Windows CMD
set SF_S3_MODE=s3mock
scripts\run.cmd
```

Give the stack more time on a slow machine:

```bash
# Linux / macOS
SF_HEALTH_TIMEOUT=420 ./scripts/run.sh
```

```powershell
# Windows PowerShell
$env:SF_HEALTH_TIMEOUT = '420'; .\scripts\run.ps1
```

> **Verification scope:** the Linux runner and the macOS wrapper were exercised
> on Linux. `run.ps1` was syntax-checked and exercised with PowerShell 7.4.6
> against the live stack on Linux. Native Windows PowerShell 5.1 + Docker
> Desktop and native macOS runs were not available in this environment; if your
> first run differs, the troubleshooting section lists the platform-specific
> checks.

Open:

| Service | URL |
|---|---|
| Dashboard | <http://127.0.0.1:3000> |
| API | <http://127.0.0.1:8000> |
| API docs (development only) | <http://127.0.0.1:8000/docs> |
| API metrics | <http://127.0.0.1:8000/metrics> |
| Selenium Grid | <http://127.0.0.1:4444/status> |
| MinIO console (when using MinIO) | <http://127.0.0.1:9001> |

---

## 4. Manual Docker setup

Use this if you do not want the runner script.

### 4.1 Create `.env`

```bash
python3 scripts/generate_env.py
```

On Windows, the native runner creates `.env` without Python, or use:

```powershell
py -3 scripts\generate_env.py
```

This writes `scrapeflow/.env` with mode `600` (or a restricted NTFS ACL on
Windows) and random values for the required secrets. It refuses to overwrite an
existing file. Never commit `.env`.

Review it before starting:

```bash
grep -E '^(APP_ENV|POSTGRES_|DATABASE_URL|REDIS_URL|API_KEY_PEPPER|JWT_SECRET|WEBHOOK_SECRET_KEY|ARTIFACTS_|SELENIUM_REMOTE_URL|EGRESS_PROXY_URL)' .env | sed -E 's/(SECRET|PEPPER|PASSWORD)=.*/\1=<redacted>/'
```

```powershell
# Windows PowerShell equivalent
Get-Content .env |
  Where-Object { $_ -match '^(APP_ENV|POSTGRES_|DATABASE_URL|REDIS_URL|API_KEY_PEPPER|JWT_SECRET|WEBHOOK_SECRET_KEY|ARTIFACTS_|SELENIUM_REMOTE_URL|EGRESS_PROXY_URL)' } |
  ForEach-Object { $_ -replace '(SECRET|PEPPER|PASSWORD)=.*', '$1=<redacted>' }
```

### 4.2 Start the development stack

```bash
docker compose --project-directory . --env-file .env up -d --build
```

If the pinned MinIO image cannot be pulled, use the platform runner
(`./scripts/run.sh`, `./scripts/run-macos.sh`, or `.\scripts\run.ps1`) or add
the S3-mock override manually. The override example below is for a POSIX shell:

```bash
cat > /tmp/sf-compose-override.yml <<'YAML'
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

docker compose --project-directory . \
  -f docker-compose.yml -f /tmp/sf-compose-override.yml \
  --env-file .env up -d --build
```

Migrations run automatically in the one-shot `migrate` service before the API,
worker, and beat start.

### 4.3 Optional demo data

```bash
docker compose exec api python -m scripts.seed
```

The seed is idempotent. It creates:

- organisation `demo` (slug `demo`)
- user `demo@example.com`
- an admin-scoped API key, printed **once**

The demo password is printed only when the user is created for the first time.
Re-running the seed creates a new API key instead of changing the password.

---

## 5. Verify the stack

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
curl -s -o /dev/null -w 'dashboard=%{http_code}\n' http://127.0.0.1:3000/login
curl -fsS http://127.0.0.1:8000/metrics | head
```

On Windows use `curl.exe` so PowerShell does not substitute its
`Invoke-WebRequest` alias:

```powershell
curl.exe -fsS http://127.0.0.1:8000/health
curl.exe -fsS http://127.0.0.1:8000/ready
curl.exe -s -o NUL -w "dashboard=%{http_code}`n" http://127.0.0.1:3000/login
```

Expected:

- `/health` → `{"status":"ok", ...}`
- `/ready` → `{"status":"ready","checks":{"postgres":{"status":"ok"},"redis":{"status":"ok"}}}`
- dashboard → `200`
- `/metrics` → Prometheus text (may require `METRICS_TOKEN` if you set one)

Container status:

```bash
docker compose --project-directory . --env-file .env ps
# or
./scripts/run.sh status
```

---

## 6. Create an account and run your first scrape

### 6.1 Dashboard

1. Open <http://127.0.0.1:3000/signup>.
2. Accept the Terms of Service.
3. Submit a URL and selectors on the scrape page.

The browser only talks to Next.js. The refresh token stays in an httpOnly
cookie and the access token stays in memory.

### 6.2 API with curl

```bash
EMAIL="you-$(date +%s)@example.com"

TOKEN=$(curl -fsS -X POST http://127.0.0.1:8000/v1/auth/signup \
  -H 'Content-Type: application/json' \
  -d "{
    \"org_name\": \"My Org\",
    \"email\": \"$EMAIL\",
    \"password\": \"correct-horse-battery-staple\",
    \"tos_accepted\": true
  }" | jq -r .access_token)

JOB=$(curl -fsS -X POST http://127.0.0.1:8000/v1/scrape \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://example.com/",
    "selectors": {"title": {"css": "title"}},
    "include_html": true
  }' | jq -r .job.id)

echo "job=$JOB"
```

Poll it:

```bash
curl -fsS "http://127.0.0.1:8000/v1/jobs/$JOB" \
  -H "Authorization: Bearer $TOKEN" | jq '{status, duration_ms, result, error}'
```

Access tokens expire after **900 seconds**. Log in again when you get `401`:

```bash
TOKEN=$(curl -fsS -X POST http://127.0.0.1:8000/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"correct-horse-battery-staple\"}" \
  | jq -r .access_token)
```

### 6.3 Browser scrape

Add `render_js` and optionally a screenshot:

```bash
curl -fsS -X POST http://127.0.0.1:8000/v1/scrape \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://example.com/",
    "render_js": true,
    "selectors": {"title": {"css": "title"}},
    "screenshot": true,
    "include_html": true,
    "timeout_seconds": 60
  }' | jq .
```

Artifacts are listed and downloaded through the API:

```bash
curl -fsS "http://127.0.0.1:8000/v1/jobs/$JOB/artifacts" \
  -H "Authorization: Bearer $TOKEN" | jq .

# Ask for the download; with S3 this is a 307 to a presigned URL
curl -s -D /tmp/artifact-headers -o /dev/null \
  "http://127.0.0.1:8000/v1/artifacts/<ARTIFACT_ID>/download" \
  -H "Authorization: Bearer $TOKEN"
grep -i '^location:' /tmp/artifact-headers

# Fetch the presigned URL. Compose signs for the internal hostname "minio",
# so map it to localhost when downloading from the host machine.
curl -fsS --resolve minio:9000:127.0.0.1 -o result.json "<PRESIGNED_URL>"
```

If the download answers directly (local filesystem store, no `Location`
header), fetch it with the bearer token instead:

```bash
curl -fsS -o result.json \
  "http://127.0.0.1:8000/v1/artifacts/<ARTIFACT_ID>/download" \
  -H "Authorization: Bearer $TOKEN"
```

### 6.4 API keys

Create a scoped key when you do not want to use a short-lived JWT:

```bash
curl -fsS -X POST http://127.0.0.1:8000/v1/keys \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"automation","scopes":["scrape:write","jobs:read"]}' | jq .
```

The plaintext key (`sf_live_...`) is returned once and never stored.

---

## 7. Configuration

Everything is read from `scrapeflow/.env`. Restart/recreate the affected
containers after changing values:

```bash
./scripts/run.sh
# or, for a targeted restart:
docker compose --project-directory . --env-file .env up -d --force-recreate api worker beat
```

### 7.1 Required secrets

| Variable | Purpose |
|---|---|
| `API_KEY_PEPPER` | Peppers API-key hashes; 32+ random characters |
| `JWT_SECRET` | Signs access tokens; 32+ random characters |
| `WEBHOOK_SECRET_KEY` | Encrypts per-org webhook signing secrets |
| `AUTOMATION_SECRET_KEY` | Seals transient automation secrets (empty = derive from JWT) |
| `POSTGRES_PASSWORD` | Must match the password in `DATABASE_URL` |
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/db` |
| `REDIS_URL` | `redis://host:6379/0` |

Generate a value with:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

`scripts/generate_env.py` fills all of these for local use.

### 7.2 Browser and egress

| Variable | Meaning |
|---|---|
| `SELENIUM_REMOTE_URL` | Grid endpoint (`http://selenium:4444/wd/hub` in Compose) |
| `EGRESS_PROXY_URL` | Validating proxy every scrape uses (`http://egress-proxy:8888`) |
| `EGRESS_ALLOWED_PORTS` | Allowed destination ports, default `80,443` |
| `JOB_TIMEOUT_SECONDS` | Hard job deadline |
| `HTTP_TIMEOUT_SECONDS` | Per-request HTTP timeout |
| `HTTP_MAX_BYTES` | Response size cap |

The API never launches Chrome. Browser execution is worker-only; the API fails
closed when a browser job cannot be routed through validated egress.

### 7.3 Artifact storage

| Variable | Meaning |
|---|---|
| `ARTIFACTS_ENDPOINT` | S3 endpoint (`http://minio:9000` in Compose) |
| `ARTIFACTS_BUCKET` | Bucket name |
| `ARTIFACTS_ACCESS_KEY` / `ARTIFACTS_SECRET_KEY` | S3 credentials |
| `ARTIFACTS_RETENTION_DAYS` | Retention for cleanup |

Leave `ARTIFACTS_ENDPOINT` empty to use the local filesystem (development and
tests only).

### 7.4 Proxies and country codes

Proxy support is **off by default**. Enable exactly one provider.

Static list — `COUNTRY|proxy-url`:

```dotenv
PROXY_ENABLED=true
PROXY_STATIC_LIST=DE|http://user:pass@proxy-a.example:8080,US|http://user:pass@proxy-b.example:8080
```

Rotating gateway — `{country}` is expanded per request:

```dotenv
PROXY_ENABLED=true
PROXY_GATEWAY_URL=http://user-{country}:pass@gateway.example.com:8080
PROXY_GATEWAY_COUNTRIES=DE,US,GB
PROXY_GATEWAY_DEFAULT_COUNTRY=US
```

Country codes are ISO 3166-1 alpha-2, exactly two uppercase letters (`US`,
`DE`, `GB`, `IN`, `AE`, `SG`). Use `GB`, not `UK`. Only advertise countries
your provider actually serves.

Request a country per job:

```json
{
  "url": "https://example.com/",
  "render_js": true,
  "proxy_country": "DE"
}
```

A country that is not configured returns `422`. With proxies disabled, sending
`proxy_country` also returns `422`. Omitting it uses the default/any endpoint.
Proxy jobs cost extra credits.

### 7.5 Plans, quotas, and billing

- Free/starter/pro/business plans and credit costs live in
  `packages/core/plans.py`.
- Quota and rate-limit failures use typed `402`/`429` responses with headers.
- Billing stays disabled until Stripe keys and price IDs are set:

```dotenv
BILLING_ENABLED=false
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_STARTER=
STRIPE_PRICE_PRO=
STRIPE_PRICE_BUSINESS=
```

### 7.6 Metrics

`METRICS_ENABLED=true` exposes `/metrics`. If the endpoint is reachable outside
a private network, set a random `METRICS_TOKEN`; requests must then send
`Authorization: Bearer <token>`.

---

## 8. Local development without Docker

The commands in this section assume a POSIX shell. On Windows, use WSL 2 or Git
Bash, or translate the environment prefixes to PowerShell
(`$env:DATABASE_URL = '...'`). The Docker path above works natively in
PowerShell.

You still need PostgreSQL and Redis. The quickest way is two containers:

```bash
docker run -d --name sf-postgres \
  -e POSTGRES_USER=scrapeflow \
  -e POSTGRES_PASSWORD=scrapeflow \
  -e POSTGRES_DB=scrapeflow \
  -p 5432:5432 postgres:16-alpine

docker run -d --name sf-redis -p 6379:6379 redis:7-alpine
```

Point `scrapeflow/.env` at the host ports and remove Compose-only hostnames:

```dotenv
DATABASE_URL=postgresql+asyncpg://scrapeflow:scrapeflow@127.0.0.1:5432/scrapeflow
REDIS_URL=redis://127.0.0.1:6379/0

# Host processes cannot resolve "egress-proxy" or "selenium".
# For HTTP jobs, either run the standalone proxy and use loopback:
EGRESS_PROXY_URL=http://127.0.0.1:8888
# ...or leave it empty so the worker starts an in-process validating proxy:
# EGRESS_PROXY_URL=
SELENIUM_REMOTE_URL=
```

Install, migrate, and start the API:

```bash
uv sync --dev
uv run alembic upgrade head
uv run python -m scripts.seed        # optional demo data
uv run uvicorn apps.api.asgi:app --reload --port 8000
```

In separate terminals:

```bash
# Worker
uv run celery -A apps.worker.celery_app worker \
  --loglevel=INFO --concurrency=1 --pool=solo --queues=jobs,celery

# Beat (reaper, schedules, webhooks, retention, quota reconcile)
uv run celery -A apps.worker.celery_app beat \
  --loglevel=INFO --schedule=/tmp/celerybeat-schedule

# Standalone validating egress proxy (needed for browser jobs with remote Grid)
EGRESS_PROXY_LISTEN_HOST=127.0.0.1 EGRESS_PROXY_LISTEN_PORT=8888 \
  uv run python -m apps.worker.egress_proxy
```

Without `EGRESS_PROXY_URL`, the worker starts an in-process validating proxy
for HTTP jobs. `render_js=false` works without Selenium; `render_js=true`
needs a Grid and `SELENIUM_REMOTE_URL`.

Dashboard:

```bash
cd apps/web
npm ci
npm run dev        # http://127.0.0.1:3000
```

`apps/web/.env.local` should contain:

```dotenv
API_BASE_URL=http://127.0.0.1:8000
NEXT_PUBLIC_APP_NAME=ScrapeFlow
```

---

## 9. Tests and quality gates

### Python

```bash
cd scrapeflow

uv run ruff check apps packages tests
uv run ruff format --check apps packages tests
uv run mypy apps packages
uv run pytest -q
```

Integration tests skip when `TEST_DATABASE_URL` / `TEST_REDIS_URL` are unset.
Run them against disposable services:

```bash
docker run -d --name sf-test-pg -p 55432:5432 \
  -e POSTGRES_USER=scrapeflow -e POSTGRES_PASSWORD=scrapeflow \
  -e POSTGRES_DB=scrapeflow_test postgres:16-alpine

docker run -d --name sf-test-redis -p 56379:6379 redis:7-alpine

TEST_DATABASE_URL='postgresql+asyncpg://scrapeflow:scrapeflow@127.0.0.1:55432/scrapeflow_test' \
TEST_REDIS_URL='redis://127.0.0.1:56379/0' \
uv run pytest -q
```

```powershell
# Windows PowerShell equivalent
$env:TEST_DATABASE_URL = 'postgresql+asyncpg://scrapeflow:scrapeflow@127.0.0.1:55432/scrapeflow_test'
$env:TEST_REDIS_URL = 'redis://127.0.0.1:56379/0'
uv run pytest -q
Remove-Item Env:TEST_DATABASE_URL, Env:TEST_REDIS_URL
```

### Web

```bash
cd scrapeflow/apps/web
npm run lint
npm run typecheck
npm test
npm run build
```

Optional browser journey (needs the API, PostgreSQL, and Redis running):

```bash
npx playwright install chromium
npm run e2e
```

Known local skips: one test needs `CHROME_BINARY` for a local Chrome run, one
worker test needs a Grid, and one load-script check needs `locust`.

---

## 10. Production deployment

This section uses `deploy/compose.prod.yml`, which runs everything behind Caddy
with automatic TLS. Run these commands on the Linux server (over SSH from
Windows or macOS); the production topology is not a desktop deployment.

### 10.1 Server prerequisites

- A Linux host with Docker + Compose v2.
- A DNS `A`/`AAAA` record for your domain pointing at the host.
- Ports `80` and `443` open.
- A production `.env`; never reuse development secrets.

### 10.2 Production `.env`

Start from `.env.example`, then set at least:

```dotenv
APP_ENV=production
PUBLIC_BASE_URL=https://scrapeflow.example.com
CORS_ORIGINS=https://scrapeflow.example.com

DOMAIN=scrapeflow.example.com
ACME_EMAIL=ops@example.com

POSTGRES_USER=scrapeflow
POSTGRES_PASSWORD=<32+ random characters>
POSTGRES_DB=scrapeflow
DATABASE_URL=postgresql+asyncpg://scrapeflow:<same password>@postgres:5432/scrapeflow
REDIS_URL=redis://redis:6379/0

API_KEY_PEPPER=<32+ random characters>
JWT_SECRET=<32+ random characters>
WEBHOOK_SECRET_KEY=<32+ random characters>
AUTOMATION_SECRET_KEY=<32+ random characters>

ARTIFACTS_BUCKET=scrapeflow
MINIO_ROOT_USER=scrapeflow
MINIO_ROOT_PASSWORD=<32+ random characters>
ARTIFACTS_ACCESS_KEY=<same as MINIO_ROOT_USER>
ARTIFACTS_SECRET_KEY=<same as MINIO_ROOT_PASSWORD>

BILLING_ENABLED=false
METRICS_ENABLED=true
METRICS_TOKEN=<32+ random characters>
```

If the pinned MinIO image is unavailable in your registry, mirror a working
image and set `MINIO_IMAGE` in `.env`.

### 10.3 Build and start

```bash
cd scrapeflow

docker compose --project-directory . -f deploy/compose.prod.yml \
  --env-file .env config >/dev/null

docker build -t scrapeflow:$(git rev-parse --short HEAD) .
docker build -t scrapeflow-web:$(git rev-parse --short HEAD) apps/web

SCRAPEFLOW_IMAGE=scrapeflow:$(git rev-parse --short HEAD) \
  docker compose --project-directory . -f deploy/compose.prod.yml \
  --env-file .env up -d
```

Only Caddy publishes ports. The API, dashboard, workers, Grid, Postgres,
Redis, and MinIO stay on the internal network.

### 10.4 Verify

```bash
curl -fsS https://$DOMAIN/health
curl -fsS https://$DOMAIN/ready
curl -fsS -H "Authorization: Bearer $METRICS_TOKEN" https://$DOMAIN/metrics | head
```

Then complete the signup → scrape → artifact flow from section 6 over HTTPS.

### 10.5 Operations

- Follow logs: `docker compose -f deploy/compose.prod.yml logs -f api worker beat caddy`
- Backup/restore, rollback, scaling, and incident procedures:
  [`docs/runbook.md`](docs/runbook.md)
- Security checklist:
  [`docs/security-checklist.md`](docs/security-checklist.md)
- Release evidence and remaining external gaps:
  [`docs/FINAL_REPORT.md`](docs/FINAL_REPORT.md)

> The development Compose stack was verified end to end with a real browser
> scrape, artifact download, live Celery Beat, and the dashboard. The production
> Caddy topology requires a real domain and was not started in this repository's
> local verification. Live Stripe, a commercial proxy gateway, a third-party
> webhook receiver, hosted CI, and Locust capacity numbers also remain
> unverified until you supply those services.

---

## 11. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `service "migrate" didn't complete successfully` | Migration failed; read its logs | `docker compose logs migrate` |
| `password authentication failed for user "scrapeflow"` | The Postgres volume was initialized with an older password than the current `.env` | `./scripts/run.sh fix-db-password` / `.\scripts\run.ps1 fix-db-password` (keeps data), or `reset` (deletes data) |
| MinIO image pull fails with `401 UNAUTHORIZED` | The pinned tag is not available from your registry | `SF_S3_MODE=s3mock ./scripts/run.sh`, `$env:SF_S3_MODE='s3mock'; .\scripts\run.ps1`, or mirror an image and set `MINIO_IMAGE` |
| `port is already allocated` on 8000/3000 | Another stack or service is using the port | Stop the stack (`./scripts/run.sh stop` or `.\scripts\run.ps1 stop`), then retry. Linux: `ss -ltnp \| grep -E ':8000\|:3000'`; Windows: `netstat -ano \| findstr :8000` |
| PowerShell: `running scripts is disabled on this system` | Execution policy blocks `.ps1` files | Run `scripts\run.cmd` or `powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1` |
| PowerShell: `SF_S3_MODE is not recognized` | Bash-style environment assignment used in PowerShell | Use `$env:SF_S3_MODE = 's3mock'` before the command |
| PowerShell: `curl` output looks like HTML or `-fsS` is rejected | `curl` is an alias for `Invoke-WebRequest` | Use `curl.exe` in commands |
| Windows: `docker` is not recognized | Docker Desktop is not running, or PATH was updated after the terminal opened | Start Docker Desktop and open a new PowerShell window |
| macOS: `python3: command not found` | Python 3 is not installed; the runner only needs it to create `.env` or repair the DB password | `xcode-select --install` or `brew install python` |
| macOS: `Cannot connect to the Docker daemon` | Docker Desktop is not running | Start Docker Desktop and wait for the whale icon to be idle |
| Browser job fails with `Browser jobs require EGRESS_PROXY_URL` | Worker did not receive the shared backend environment | Use the committed Compose files or set `EGRESS_PROXY_URL` on the worker |
| Job ends `UPSTREAM_ERROR` after a timeout | The page never matched `wait_for` | Remove/relax `wait_for`; `example.com` has no `<h1>` |
| `401 Unauthorized` after a while | Access token expired (900 s) | Log in again or use an API key |
| `402` / `429` responses | Plan quota or rate limit | Inspect `Retry-After` / quota headers, or raise the plan |
| Dashboard returns `502` | API is not healthy | Run the `status` command for your platform and check API logs |
| `DevToolsActivePort file doesn't exist` | Chrome was not started headless, or Grid lacks shared memory | Keep `--headless=new`, `--disable-gpu`; Grid needs `shm_size: 2g` |
| `Future attached to a different loop` in worker logs | Old worker image reused a pooled connection across Celery task loops | Rebuild with the current code (run the start command again) |

Useful diagnostics:

```bash
./scripts/run.sh status
./scripts/run.sh logs
docker compose --project-directory . --env-file .env logs --tail=100 migrate
docker inspect scrapeflow-worker-1 --format '{{range .Config.Env}}{{println .}}{{end}}' | sort
```

```powershell
# Windows PowerShell
.\scripts\run.ps1 status
.\scripts\run.ps1 logs
docker compose --project-directory . --env-file .env logs --tail=100 migrate
docker inspect scrapeflow-worker-1 --format '{{range .Config.Env}}{{println .}}{{end}}'
```

---

## 12. Routine controls

```bash
# Start or update
./scripts/run.sh

# Stop without losing data
./scripts/run.sh stop

# Delete containers and local data volumes (destructive)
./scripts/run.sh reset

# Recreate one service after an env change
docker compose --project-directory . --env-file .env up -d --force-recreate api worker beat

# Seed demo account (first run prints the password; each run prints a new key)
./scripts/run.sh seed

# View database migrations
docker compose exec api alembic current
docker compose exec api alembic heads
```

On Windows replace each `./scripts/run.sh` command with
`.\scripts\run.ps1`; the direct `docker compose` commands are identical.

Data lives in named Docker volumes: `scrapeflow_pgdata`,
`scrapeflow_redisdata`, and `scrapeflow_miniodata` (or the S3-mock container).
Back them up before `reset`.

---

## 13. Security checklist before publishing

- [ ] `.env` is **not** tracked:

  ```bash
  git check-ignore -v scrapeflow/.env
  git status --short
  ```

- [ ] `scrapeflow/.env.legacy`, `.venv/`, `node_modules/`, `.next/`, `.run/`,
      coverage files, screenshots, and database dumps are not tracked.
- [ ] All development secrets in `.env` are random, not reused, and different
      from production.
- [ ] No API keys, JWT secrets, Stripe keys, proxy credentials, or webhook
      secrets appear in commits, issue text, or screenshots.
- [ ] Production secrets are injected through the server environment or a
      secret manager, never baked into images.
- [ ] `APP_ENV=production` in production (disables `/docs` and enforces secure
      cookies).
- [ ] `/metrics` is private or protected by `METRICS_TOKEN`.
- [ ] `BILLING_ENABLED=false` until real Stripe keys are configured.
- [ ] Rotate any secret that was ever committed by accident.

If a secret was committed, rotate it first, then rewrite history; deleting the
file in a later commit is not enough.

---

## 14. Publish the repository to GitHub

The local branch may be named `master`. GitHub's default is `main`; the CI
workflow accepts both, but renaming avoids surprises.

```bash
cd web-scrapping-tool

# 1. Make sure the working tree is clean and secrets are ignored
git status --short
git check-ignore -v scrapeflow/.env

# 2. Use main
git branch -M main

# 3. Create an empty repository on GitHub (no README, no .gitignore),
#    then connect it:
git remote add origin git@github.com:<YOUR_USER>/<YOUR_REPO>.git
# HTTPS alternative:
# git remote add origin https://github.com/<YOUR_USER>/<YOUR_REPO>.git

# 4. Push
git push -u origin main
```

If the remote already exists:

```bash
git remote set-url origin git@github.com:<YOUR_USER>/<YOUR_REPO>.git
git push -u origin main
```

After the push, open the **Actions** tab. `.github/workflows/ci.yml` runs:

| Job | What it does |
|---|---|
| `backend` | Ruff, mypy, unit tests with coverage, `pip-audit` |
| `integration` | PostgreSQL + Redis services, integration tests |
| `web` | ESLint, typecheck, Vitest, production build |
| `image` | Builds the backend and dashboard Docker images |

Notes:

- The workflow runs on pushes to `main` or `master` and on pull requests.
- No repository secrets are required for the default CI path.
- Hosted CI has not been executed from this local checkout; watch the first run
  and fix any runner-specific issues.
- Add a branch protection rule requiring CI before merge.

---

## 15. Project layout and further reading

```
scrapeflow/
  apps/api        FastAPI app, routers, services, middleware
  apps/worker     Celery tasks, browser runner, egress proxy
  apps/web        Next.js dashboard + same-origin BFF
  packages/core   settings, DB, models, quotas, SSRF, security
  migrations      Alembic migrations
  tests           unit / integration / e2e / load
  deploy          production Compose, Caddy, Prometheus, Grafana
  scripts         run.sh, run-macos.sh, run.ps1, run.cmd, env generator, seed, bucket setup
docs/
  runbook.md      deploy, rollback, backup, incident response
  security-checklist.md
  FINAL_REPORT.md verified scope and remaining external gaps
  analysis/       gap matrix, system map, plan, risk review
```

Useful entry points:

- API documentation (development): <http://127.0.0.1:8000/docs>
- OpenAPI JSON: <http://127.0.0.1:8000/openapi.json>
- Health: `/health`; readiness: `/ready`; metrics: `/metrics`
- Scrape: `POST /v1/scrape`; jobs: `GET /v1/jobs/{id}`; artifacts:
  `GET /v1/jobs/{id}/artifacts`
- Automation: `POST /v1/automate`
- Schedules, exports, webhooks: see [`scrapeflow/README.md`](scrapeflow/README.md)
