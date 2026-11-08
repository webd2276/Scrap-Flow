# ScrapeFlow final report

Date: 2026-11-07
Scope: Phases 1–9 of `docs/analysis/04-plan.md` in this repository.

## 1. Outcome

ScrapeFlow is a multi-tenant scraping and browser-automation platform with:

- A FastAPI control plane that never launches Chrome.
- Durable PostgreSQL jobs, Celery workers, a Selenium Grid browser path, and a
  hard job timeout with an orphan-session reaper.
- Tenant auth with JWTs and hashed API keys, scoped roles, rate limits, plan
  quotas and Stripe billing integration.
- Typed scrape and automation schemas, change detection, schedules, signed
  webhooks with a durable outbox, and streaming exports.
- SSRF-safe egress: every HTTP and browser destination resolves through a
  validating proxy that denies private addresses and pins the validated IP.
  Optional upstream proxies chain behind it, never around it.
- A Next.js dashboard using a same-origin BFF; refresh tokens stay in an
  httpOnly cookie and access tokens stay in memory.
- Phase 9 observability: Prometheus metrics, correlated JSON logs, PII-free
  Sentry, alert rules, a provisioned Grafana dashboard, a Locust profile, and
  deploy/rollback/backup/incident runbooks.

All phases are implemented and committed. The remaining unverified items are
external integrations that require credentials or infrastructure not available
on this host; they are listed in section 5 rather than claimed as working.

## 2. Architecture

```text
Browser -> Caddy (TLS)
             |-- /v1/*, /health, /ready, /metrics, /docs -> FastAPI
             |-- everything else -> Next.js web (BFF)
FastAPI -> PostgreSQL (durable jobs, ledger, schedules, outbox)
        -> Redis (broker, quota/token buckets, locks, sessions)
        -> Celery queue
Celery worker -> Selenium Grid -> validating egress proxy -> public internet
              -> PostgreSQL / Redis / artifact store
Celery Beat -> schedules, reaper, reconciliation, retention, webhook delivery
```

The API process does not import or start Selenium. Browser jobs fail closed with
503 if the Grid or egress proxy is unavailable. Job payloads never contain
automation secrets; sealed secrets live in Redis for one execution.

## 3. Verification evidence

All Python checks ran in a Python 3.12 virtual environment against pinned
PostgreSQL 16 and Redis 7 containers on `127.0.0.1:55432/56379`.

```bash
cd scrapeflow
.venv/bin/ruff check apps packages tests
.venv/bin/ruff format --check apps packages tests
.venv/bin/mypy apps packages
TEST_DATABASE_URL='postgresql+asyncpg://scrapeflow@127.0.0.1:55432/scrapeflow_test' \
TEST_REDIS_URL='redis://127.0.0.1:56379/0' \
.venv/bin/pytest -q --cov=apps --cov=packages --cov-report=term-missing
```

Result: **313 passed, 3 skipped, 83.02% branch/line coverage**.

Skips:

1. Real local Chrome/Grid browser execution (`CHROME_BINARY` not set).
2. A second Grid-dependent worker test.
3. The optional Locust import check (Locust is not installed in this venv).
   The load script's structure is still tested by parsing it.

Additional checks:

| Check | Command | Result |
|---|---|---|
| Dev compose render | `docker compose --project-directory . -f docker-compose.yml --env-file .env config` | Passed |
| Prod compose render | `docker compose --project-directory . -f deploy/compose.prod.yml --env-file .env config` with required MinIO/env values | Passed |
| Observability overlay render | prod file + `deploy/compose.observability.yml` | Passed |
| Prometheus YAML + Grafana JSON | parsed with `yaml.safe_load` / `json.loads`; `promtool check config` | Passed; config valid with 9 rules |
| Worker metrics live endpoint | ran `start_worker_metrics_server`, scraped `127.0.0.1:9199/metrics` | Passed; observed `scrapeflow_http_requests_total` sample |
| API metrics live endpoint | ran uvicorn against PostgreSQL/Redis, scraped `/metrics` | HTTP 200; queue, session, webhook, DB and Redis gauges populated |
| Backend image | CI builds `scrapeflow/Dockerfile` | Workflow updated; hosted run unverified |
| Web image | `docker build -t scrapeflow-web:phase8 apps/web` | Passed |
| Web read-only smoke | container serving `/login` | HTTP 200 |
| Web gates | `npm run lint`, `npm run typecheck`, `npm test`, `npm run build` | Passed; 30 Vitest tests, 16 routes built |
| Web E2E | `npx playwright test --project=chromium` against a live API | 5 passed, 2 skipped (env-authenticated specs) |

Phase 9 tests specifically cover:

- `/metrics` content and all required series, cartesian labels, token
  enforcement, disabled=404, no token echo, and exclusion from its own counters.
- Real PostgreSQL/Redis runtime sampling and quota-rejection metrics through the
  API path.
- JSON access logs containing `request_id`, request-header echo, invalid-ID
  replacement, and worker `job_id` binding across post-terminal hooks.
- Sentry initialisation with `send_default_pii=False`.
- Worker multiprocess metrics branch and the load-script shape.

## 4. Security review summary

The full checklist is `docs/security-checklist.md`. Key verified controls:

- Tenant scoping and scope checks on API and dashboard routes.
- Short-lived JWTs, rotating hashed refresh tokens, one-time API keys stored as
  peppered hashes.
- Secrets held as `SecretStr`, sealed automation secrets, encrypted webhook
  signing secrets, no secrets in logs/results/job payloads.
- SSRF validation at connection time with private/metadata denial, DNS
  rebinding mitigation, IP pinning, redirects revalidated or disabled, bounded
  bodies, and robots/AUP enforcement.
- Atomic Redis rate limits and plan quotas with typed 402/429 responses and
  headers; idempotent job creation.
- Formula-injection-safe streaming exports and tenant-checked artifact
  downloads.
- Same-origin BFF, httpOnly refresh cookie, in-memory access token, allowlisted
  proxy headers, HTTPS-only billing redirects, safe download filenames.
- Caddy TLS/HSTS, non-root/read-only containers, dropped capabilities, no
  public API/worker ports.
- PII-free Sentry, bounded metric labels, bearer-token-protected `/metrics`,
  and correlated logs without customer payloads.

Residual risks are listed at the end of the checklist, including operator key
custody and TCP-only proxy health checks.

## 5. Unverified external paths

These are not claimed as working because they were not exercised end to end:

1. **Live Stripe checkout/portal**: no Stripe test keys. Signed webhook events,
   idempotency, and billing state transitions are unit/integration tested.
2. **Selenium Grid in compose**: no full compose/Grid startup. The browser
   engine, step semantics, timeout, and reaper are tested with fakes and a local
   Chrome path when `CHROME_BINARY` is supplied.
3. **MinIO/S3 upload, presign, and lifecycle**: no live bucket. Local artifact
   storage and the storage abstraction are tested.
4. **Live Celery Beat + real external webhook receiver**: dispatch, dedupe,
   retries, DLQ, and HMAC signing are tested; a real receiver was not run.
5. **Commercial proxy gateway**: no provider account. Parsing, rotation,
   health failover, retry safety, and upstream forwarding are tested; the
   gateway's real egress policy is not.
6. **Full production compose/Grid/Caddy stack** and **hosted CI run**: both
   configurations render, images build, and CI is configured, but the full
   startup and the GitHub Actions execution were not observed here.
7. **Real load numbers**: the Locust profile exists and parses, but capacity
   must be measured on the target infrastructure.

## 6. Operations

Use `docs/runbook.md` for deploy, rollback, PostgreSQL backup/restore, Redis and
MinIO recovery, scaling, alert responses, and incident steps. The observability
overlay is optional and binds Prometheus/Grafana to loopback:

```bash
docker compose --project-directory . \
  -f deploy/compose.prod.yml -f deploy/compose.observability.yml \
  --env-file .env up -d prometheus grafana
```

Set `GRAFANA_ADMIN_PASSWORD`; keep `METRICS_TOKEN` when `/metrics` is exposed
through Caddy. Client examples are in `docs/examples/`.

## 7. Release recommendation

The codebase is ready for a staged release candidate with the following gates:

1. Run the CI workflow on GitHub Actions and require it to pass.
2. Bring up the full compose stack on a staging host and exercise Selenium Grid,
   MinIO, live Beat, and an external webhook receiver.
3. Configure Stripe test keys and complete a checkout/portal/webhook round trip.
4. Run the Locust profile against staging and record p95 latency, error rate,
   queue depth, and worker/Grid saturation.
5. Complete the quarterly PostgreSQL restore drill and confirm alert delivery.

Until those gates pass, the external integrations remain documented as
**UNVERIFIED**.
