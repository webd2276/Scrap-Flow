# ScrapeFlow

Multi-tenant web scraping and browser-automation API. This repository is being
rebuilt from the original single-process MVP into the production architecture
described in `docs/analysis/04-plan.md`.

**Status: Phase 6 complete — schedules, change detection, signed webhooks, and exports.**
Phase 6 adds cron-based recurring jobs with IANA timezones and schema-validated
templates, at-most-once occurrence dispatch, watched-field snapshots and diffs,
an org-level HMAC signing secret, a durable webhook outbox with retries/DLQ and a
delivery log, and streaming CSV/JSON job and schedule exports with spreadsheet
formula escaping. The full suite is 265 passed with 2 infrastructure skips and
82.32% branch coverage. Live Stripe checkout, Selenium Grid, and MinIO/S3 compose
paths remain **UNVERIFIED** (no Stripe test keys; Docker denied). See
`docs/analysis/02-gap-matrix.md` for the live gap list.

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

# Beat (reaper, schedule dispatch, webhook delivery, retention, reconcile)
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
| POST | `/v1/automate` | `automation:write` | accept a typed browser automation job (202) |
| GET | `/v1/jobs` | `jobs:read` | list tenant jobs (status filter, paging) |
| GET | `/v1/jobs/{id}` | `jobs:read` | job status + result/error |
| POST | `/v1/jobs/{id}/cancel` | `scrape:write` | cancel queued/running job |
| GET | `/v1/jobs/{id}/events` | `jobs:read` | lifecycle events |
| GET | `/v1/jobs/{id}/artifacts` | `jobs:read` | artifact metadata |
| GET | `/v1/artifacts/{id}/download` | `jobs:read` | presigned redirect or stream |
| GET | `/v1/billing/plans` | none | plan catalog and limits |
| GET | `/v1/billing/usage` | `billing:manage` | current period usage and limits |
| POST | `/v1/billing/checkout` | `billing:manage` | create a Stripe checkout session |
| POST | `/v1/billing/portal` | `billing:manage` | create a Stripe billing portal session |
| POST | `/v1/billing/webhook` | Stripe signature | idempotent subscription lifecycle |
| POST | `/v1/schedules` | `schedules:write` | create a cron schedule |
| GET | `/v1/schedules` | `jobs:read` | list tenant schedules |
| GET | `/v1/schedules/{id}` | `jobs:read` | schedule detail and next run |
| PATCH | `/v1/schedules/{id}` | `schedules:write` | edit cron/timezone/template/enabled |
| DELETE | `/v1/schedules/{id}` | `schedules:write` | delete a schedule |
| POST | `/v1/schedules/{id}/run` | `schedules:write` | run a schedule immediately |
| GET | `/v1/schedules/{id}/runs` | `jobs:read` | run history |
| GET | `/v1/schedules/{id}/history` | `jobs:read` | alias for run history |
| POST | `/v1/webhooks` | `schedules:write` | register an HTTPS endpoint |
| GET | `/v1/webhooks` | `schedules:write` | list endpoints |
| PATCH | `/v1/webhooks/{id}` | `schedules:write` | edit URL/events/enabled |
| DELETE | `/v1/webhooks/{id}` | `schedules:write` | delete an endpoint |
| POST | `/v1/webhooks/rotate-secret` | `schedules:write` | rotate the org signing secret |
| GET | `/v1/webhooks/deliveries` | `jobs:read` | delivery log and DLQ state |
| GET | `/v1/jobs/{id}/export?format=csv\|json` | `exports:read` | stream a job export |
| GET | `/v1/schedules/{id}/export?format=csv\|json` | `exports:read` | stream schedule-run history |

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

### Automation example

```bash
curl -s -X POST localhost:8000/v1/automate \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{
    "url":"https://93.184.216.34/",
    "steps":[
      {"action":"type","selector":"#email","text":"{{email}}"},
      {"action":"click","selector":"#submit","retries":1},
      {"action":"wait_for","selector":"#message"},
      {"action":"get_text","name":"message","selector":"#message"},
      {"action":"screenshot","name":"after-submit"}
    ],
    "secrets":{"email":"user@example.com"}
  }'
```

Actions: `goto`, `click`, `type`, `press`, `select`, `hover`, `wait_for`,
`sleep`, `scroll`, `extract`, `get_text`, `screenshot`, `execute_if_present`,
`loop_pages`. Each step supports `optional`, `timeout_s`, and `retries`.
Secrets may be referenced as `{{name}}` only in `type.text`, `select.value`, and
`press.key`; values are sealed with AES-GCM in Redis, bound to the job id, and
deleted when the job finishes. Step records never include input text. A failing
step produces a `failure_screenshot` artifact plus a partial result.

### Plans, credits, and quotas

| Plan | Monthly credits | Concurrency | Steps | Pages | Artifact retention |
|---|---:|---:|---:|---:|---:|
| Free | 100 | 1 | 10 | 5 | 1 day |
| Starter | 5,000 | 3 | 50 | 25 | 7 days |
| Pro | 50,000 | 10 | 100 | 100 | 30 days |
| Business | 250,000 | 25 | 200 | 500 | 90 days |

Credits are reserved atomically when a job is accepted: 1 base + 1 for browser
rendering + 1 per screenshot + 2 per proxied request + 1 per extra page + 1 per
10 automation steps. A reservation is released if the job never starts; once a
worker begins execution it is committed on success, failure, timeout, or
cancellation. Redis counters are authoritative for the current month and the
`usage_ledger` row in PostgreSQL is the durable record; a beat task reconciles
the two and repairs a cold or drifted Redis counter.

Accepted jobs return quota headers (`X-Quota-Limit`, `X-Quota-Remaining`,
`X-Quota-Reset`, `X-Concurrency-Limit`, `X-Concurrency-Remaining`). Limit
violations return `402 QUOTA_EXCEEDED`, concurrency saturation returns
`429 CONCURRENCY_LIMIT`, and both include `Retry-After`.

Billing is disabled by default (`BILLING_ENABLED=false`). When enabled, set
`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, and the per-plan
`STRIPE_PRICE_*` IDs. `POST /v1/billing/webhook` verifies `Stripe-Signature`
with a replay tolerance, stores `stripe_events(event_id)` for idempotency, and
retries a previously failed event. Checkout and portal require
`billing:manage`; a portal request without a Stripe customer returns `409`.
Artifacts are purged after the plan retention window by a beat task.

### Schedules, change detection, webhooks, and exports

Schedules store a cron expression, an IANA timezone, and a job template that is
validated with the same `ScrapeRequest`/`AutomationRequest` schema used at
submission. Automation templates may not embed `secrets`, and no schedule may
use `webhook_url`; those values must go through the webhook registry. The beat
dispatcher claims each due occurrence before creating the job: `schedule_runs`
has a unique `run_key`, so a crashed or concurrent dispatcher cannot create two
jobs for the same occurrence. Quota or plan failures are recorded as `skipped`
runs with the typed error instead of silently disappearing.

Watched fields use dot/bracket paths (`price.value`, `items[0].name`). The first
successful run stores a baseline; later runs store `appeared`, `disappeared`, and
`changed` diffs. `notify_on_change=false` still records history but suppresses
`schedule.changed` webhooks.

Webhook endpoints must be HTTPS and pass the same SSRF validator as scrape
targets. Each org is limited to 20 endpoints so one tenant cannot multiply
delivery fan-out without bound, and endpoint creation locks the org row so
concurrent requests cannot mint competing signing secrets. The first endpoint
(or an explicit rotate) generates a 32-byte org secret and returns it exactly
once. The secret is encrypted at rest with
AES-256-GCM under `WEBHOOK_SECRET_KEY` because HMAC needs the plaintext; it is
never hashed, logged, or returned again. Deliveries are written to a durable
outbox with a dedupe key, signed with
`X-ScrapeFlow-Signature: sha256=<hmac(timestamp.body)>`, and retried with
exponential jitter for timeouts, `408`, `425`, `429`, and `5xx` until
`WEBHOOK_MAX_ATTEMPTS`, then parked in the dead-letter state. Each attempt
revalidates the URL and can be inspected through the delivery log. A job-level
`webhook_url` now requires a configured signing secret.

Exports stream rows from PostgreSQL without loading the full result set. CSV
cells are neutralised against spreadsheet formula injection (`=`, `+`, `-`, `@`,
leading tab/CR), responses set `Content-Disposition` with a sanitised filename
and `X-Content-Type-Options: nosniff`, and every export is tenant-scoped.

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
- Automation secrets never enter the job payload or database. The API seals them
  with AES-256-GCM under a key derived from `AUTOMATION_SECRET_KEY` (or HKDF from
  `JWT_SECRET`), binds the ciphertext to the job id, and the worker deletes the
  Redis key in a `finally` block. Retries only use the in-memory map for that
  execution, and failure messages are redacted.
- Webhook signing secrets are encrypted at rest, returned only once, and never
  logged. Endpoint URLs must be HTTPS and are revalidated before every delivery.
  Signatures cover the timestamp and exact body with a bounded replay window;
  redirects are disabled and response bodies are capped.

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

Real browser test (Chrome for Testing + chromedriver; skipped without
`CHROME_BINARY`):

```bash
CHROME_BINARY=/path/to/chrome-linux64/chrome \
CHROMEDRIVER_BINARY=/path/to/chromedriver-linux64/chromedriver \
uv run pytest -m browser
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
