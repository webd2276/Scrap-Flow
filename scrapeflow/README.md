# ScrapeFlow

Multi-tenant web scraping and browser-automation API. This repository is being
rebuilt from the original single-process MVP into the production architecture
described in `docs/analysis/04-plan.md`.

**Status: Phase 3 complete — durable scrape jobs, worker, SSRF-safe egress, artifacts.**
Phase 3 adds `POST /v1/scrape`, job reads/cancel/events, local and S3/MinIO
artifacts, a hardened egress proxy, and Selenium Grid wiring. Browser/Grid and
MinIO paths are implemented but **UNVERIFIED on this host** (Docker denied, no
Chrome). See `docs/analysis/02-gap-matrix.md` for the live gap list.

## Requirements

- Docker + Docker Compose (full stack), or
- Python 3.12 + `uv`, PostgreSQL, and Redis for local development.

## Quick start (Docker)

```bash
cp .env.example .env
python3 scripts/generate_env.py     # creates .env with random secrets; never overwrites
docker compose up --build
docker compose exec api python -m scripts.seed   # prints demo password + API key once
```

Migrations run automatically in the one-shot `migrate` service before the API,
worker, and beat start.

Then:

```bash
curl -s localhost:8000/health
curl -s localhost:8000/ready
```

API docs: <http://localhost:8000/docs> (disabled in production).

## Local development

```bash
uv sync --dev
python3 scripts/generate_env.py     # only if .env does not exist
uv run alembic upgrade head
uv run python -m scripts.seed       # demo org, user, and scoped API key
uv run uvicorn apps.api.asgi:app --reload --port 8000
```

The API fails fast if `DATABASE_URL`, `REDIS_URL`, `API_KEY_PEPPER`,
`JWT_SECRET`, or `WEBHOOK_SECRET_KEY` are missing or shorter than 32 characters.

Run the queue and worker in separate terminals:

```bash
# API
uv run uvicorn apps.api.asgi:app --reload --port 8000

# Worker (consumes both the jobs and default queues)
uv run celery -A apps.worker.celery_app worker --loglevel=INFO \
  --concurrency=1 --pool=solo --queues=jobs,celery

# Beat (reaper + future schedules)
uv run celery -A apps.worker.celery_app beat --loglevel=INFO \
  --schedule=/tmp/celerybeat-schedule
```

Without `EGRESS_PROXY_URL` the worker starts an in-process validating proxy for
HTTP jobs. For browser jobs against remote Selenium, set `EGRESS_PROXY_URL` or
run the standalone proxy:

```bash
EGRESS_PROXY_LISTEN_HOST=127.0.0.1 EGRESS_PROXY_LISTEN_PORT=8888 \
  uv run python -m apps.worker.egress_proxy
```

## Authentication

- **Users:** `POST /v1/auth/signup`, `POST /v1/auth/login`, cookie-based refresh
  rotation, `POST /v1/auth/logout`, `GET /v1/auth/me`.
- **API keys:** `sf_live_<prefix>_<secret>`; SHA-256 with a server pepper. The
  plaintext is returned only once. Keys are scoped, expiring, revocable, and
  track `last_used_at`.
- **Access tokens:** short-lived HS256 JWTs with `kid` so signing keys can be
  rotated (`JWT_ACTIVE_KID`, `JWT_PREVIOUS_KEYS` JSON map).
- **Refresh reuse:** replaying a rotated refresh token revokes the entire active
  family for that user.

## Current endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | none | liveness |
| GET | `/ready` | none | Postgres + Redis readiness |
| POST | `/v1/auth/signup` | none (IP-limited) | create org + owner |
| POST | `/v1/auth/login` | none (IP-limited) | issue access + refresh |
| POST | `/v1/auth/refresh` | refresh cookie/body | rotate refresh token |
| POST | `/v1/auth/logout` | refresh cookie/body | revoke refresh token |
| GET | `/v1/auth/me` | Bearer JWT | profile and memberships |
| POST | `/v1/keys` | `keys:manage` | create scoped key |
| GET | `/v1/keys` | `keys:manage` | list keys (never plaintext) |
| DELETE | `/v1/keys/{id}` | `keys:manage` | revoke a key |
| POST | `/v1/scrape` | `scrape:write` | accept a durable scrape job (202) |
| GET | `/v1/jobs` | `jobs:read` | list tenant jobs (status filter, paging) |
| GET | `/v1/jobs/{id}` | `jobs:read` | job status + result/error |
| POST | `/v1/jobs/{id}/cancel` | `scrape:write` | cancel queued/running job |
| GET | `/v1/jobs/{id}/events` | `jobs:read` | lifecycle events |
| GET | `/v1/jobs/{id}/artifacts` | `jobs:read` | artifact metadata |
| GET | `/v1/artifacts/{id}/download` | `jobs:read` | presigned redirect or stream |

`POST /v1/scrape` accepts CSS/XPath selectors, `render_js`, `wait_for`,
screenshots, HTML capture, bounded pagination, and request headers. Reusing an
`Idempotency-Key` returns `200` with `Idempotent-Replay: true` instead of
creating a second job. `screenshot`/`wait_for` require `render_js=true`;
`proxy_country` currently returns `422` because no proxy provider is configured.

### Scrape example

```bash
curl -s -X POST localhost:8000/v1/scrape \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com/","selectors":{"title":{"css":"title"}},"include_html":true}'
```

### Security model

- The API validates scheme/port/host and denies non-global addresses before
  accepting work.
- The worker performs every outbound request through an egress proxy that
  resolves again at connect time and pins the checked IP, closing DNS-rebinding
  gaps. HTTP redirects are validated per hop; browser jobs revalidate the final
  URL. Compose exposes the proxy only on the internal network and allows
  `80,443`.
- The API process never imports Selenium. Browser jobs require
  `SELENIUM_REMOTE_URL` plus `EGRESS_PROXY_URL`; otherwise the job fails with
  `503` instead of bypassing validation.
- Artifact storage keys are server-generated, traversal-checked, and scoped to
  `org/job`. S3/MinIO downloads use short-lived presigned redirects; the local
  backend streams with `attachment`, `nosniff`, and a sandbox CSP.

Rate limits are atomic Redis token buckets per organisation and per IP, with
`X-RateLimit-*` and `Retry-After` headers. Limits are configured in
`.env.example`.

## Quality gates

```bash
make lint     # ruff check + format check
make type     # mypy strict
make test     # pytest (unit)
make cov      # pytest with coverage

# Integration tests need real services:
TEST_DATABASE_URL='postgresql+asyncpg://scrapeflow@127.0.0.1:55432/scrapeflow_test' \
TEST_REDIS_URL='redis://127.0.0.1:56379/0' \
uv run pytest tests/integration
```

## Layout

```
apps/api        FastAPI app (middleware, routers, services)
apps/worker     Celery workers and Selenium runner
apps/web        Next.js dashboard (later phase)
packages/core   settings, errors, logging, db, security, rate limiting
migrations      Alembic
tests           unit / integration / e2e
deploy          production compose, Caddy, dashboards
```

## Production notes

- The production compose file must be rendered from the repository root:
  `docker compose --project-directory . -f deploy/compose.prod.yml --env-file .env config`
- Only Caddy publishes ports; the API is reachable only on the internal network.
  Uvicorn trusts `X-Forwarded-For` from that network so per-IP limits see the
  real client address.
- Docker daemon access is unavailable on the current development host, so
  `docker compose up --build` and image builds remain **UNVERIFIED** here. CI
  and the local Python/PostgreSQL/Redis/Selenium paths are used instead.
