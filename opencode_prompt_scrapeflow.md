# OpenCode Prompt: ScrapeFlow Production Build

Paste everything below this line into OpenCode.

---

## ROLE

You are a senior backend/platform engineer. You will build **ScrapeFlow**, a production-grade, multi-tenant web scraping and browser automation API that I will sell to marketing teams and agencies. Work autonomously, in phases, and verify each phase before moving on. Prefer boring, proven technology. Never leave stubs, TODOs, or fake implementations: if something cannot be done, say so explicitly.

## PRODUCT

A customer gives a URL (website, web app, or single page). ScrapeFlow opens it in a real browser (Selenium), extracts data, and can run scripted browser workflows (click, type, scroll, wait, extract, screenshot). Customers integrate via REST API, and also use a small web dashboard.

Core use cases for marketers: lead/contact extraction from public pages, competitor price and content monitoring, SEO/meta audits, directory data collection, scheduled recurring scrapes, and repetitive web-form workflows on sites the customer owns or is authorized to use.

## TECH STACK (fixed, do not substitute without asking)

- Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x (async), Alembic
- PostgreSQL 16 (system of record), Redis 7 (queue, rate limits, locks)
- Celery (or Arq) workers; Celery Beat for schedules
- Selenium 4 with **Selenium Grid** (standalone-chrome nodes) so browsers are isolated from the API process
- Docker + docker-compose (dev) and a production compose file; Caddy or Traefik for TLS
- Frontend dashboard: Next.js (App Router) + TypeScript + Tailwind, minimal and clean
- Billing: Stripe (subscriptions + metered usage)
- Observability: structured JSON logs, Prometheus metrics, Sentry hooks, `/health` and `/ready`
- Testing: pytest, pytest-asyncio, httpx, testcontainers; Playwright only for dashboard E2E
- CI: GitHub Actions (lint, type-check, test, build images)
- Tooling: ruff, mypy (strict on app code), pre-commit

## ARCHITECTURE

```
Client / Dashboard
       |
   FastAPI (auth, validation, rate limit, enqueue)
       |            \
   Postgres        Redis (queue, limits)
       |               |
   Celery workers -> Selenium Grid (Chrome nodes, ephemeral sessions)
       |
   Result storage (Postgres for JSON; S3-compatible object store for screenshots/HTML)
       |
   Webhooks / polling / CSV-JSON export
```

Rules:
- API process never launches Chrome. Workers talk to Selenium Grid.
- One browser session per job, always closed in `finally`, with hard wall-clock job timeout and a reaper for orphaned sessions.
- Everything async from the client's view: `POST` returns `job_id` (202); results via `GET`, webhook, or export.
- Idempotency: support an `Idempotency-Key` header on job creation.

## FEATURES

### 1. Scrape endpoint
`POST /v1/scrape` with: `url`, `selectors` (CSS or XPath, with `attr`, `all`), `wait_for`, `render_js` (bool), `screenshot`, `include_html`, `extract` options (`links`, `meta`, `text`, `emails`, `phones`, `structured_data` for JSON-LD/OpenGraph), `pagination` (next-button selector, max pages), `webhook_url`, `proxy_country` (optional).

### 2. Automation endpoint
`POST /v1/automate` with an ordered list of steps: `goto, click, type, press, select, hover, wait_for, sleep, scroll, extract, get_text, screenshot, execute_if_present, loop_pages`. Validate every step with a discriminated Pydantic union (no free-form dicts). Per-step `optional`, `timeout`, `retries`. On failure return the step log plus a failure screenshot. Secrets used in `type` steps (passwords, tokens) are accepted via a `secrets` map, referenced as `{{secret.NAME}}`, never stored, never logged, redacted in responses.

### 3. Schedules and monitoring
`POST /v1/schedules` for cron-style recurring jobs. Store history, diff against previous result, and fire a webhook/email when watched fields change (price changed, element appeared/disappeared).

### 4. Exports
CSV and JSON export per job and per schedule history. Streaming for large results.

### 5. Multi-tenancy and accounts
Organizations, users, roles (owner, admin, member). API keys are per org, hashed at rest (store only a hash plus a prefix), revocable, with scopes and last-used timestamps. JWT sessions for the dashboard.

### 6. Plans, quotas, billing
Plans (Free, Starter, Pro, Business) defined in config with: monthly job credits, max concurrent jobs, max steps per job, max pages per job, screenshot retention. Credits per job depend on features used (JS rendering, screenshots, proxies). Atomic quota checks in Redis, reconciled to Postgres. Stripe checkout, customer portal, webhook handling (signature verified, idempotent). Clear 402/429 responses with `Retry-After` and remaining-quota headers.

### 7. Proxies
Pluggable proxy provider interface (static list, authenticated rotating gateway). Per-job proxy assignment, health checks, automatic retry with a different proxy on connection failure. No CAPTCHA-solving and no fingerprint-spoofing code.

### 8. Dashboard
Pages: login/signup, API keys, run a scrape (form with live JSON preview), build automation steps (simple step builder), job list and detail (status, logs, screenshot, result viewer, export), schedules, usage and billing. Keep it fast and plain; no heavy UI frameworks beyond Tailwind and a small component set.

## SECURITY (non-negotiable)

- **SSRF protection**: resolve and validate every URL (initial, redirects, final, and webhook URLs); block private, loopback, link-local, metadata (169.254.169.254), and reserved ranges, IPv4 and IPv6; re-validate after redirects; pin DNS resolution where possible. Run Selenium Grid on an isolated Docker network with egress rules that block internal ranges at the network level, because page JavaScript can bypass application checks.
- Only `http`/`https`. Block `file:`, `chrome:`, `javascript:`, `data:` navigation.
- Validate and cap all inputs: URL length, steps count, selector length, sleep seconds, response sizes, pages, screenshot size.
- Hash API keys (SHA-256 with server-side pepper), constant-time comparison, never log keys or secrets.
- Per-org and per-IP rate limiting (Redis token bucket).
- Webhook payloads signed with HMAC (`X-ScrapeFlow-Signature`) and timestamp to prevent replay.
- Run containers as non-root, read-only filesystem where possible, dropped capabilities, resource limits, `shm_size` for Chrome.
- Secrets only via environment or secret manager; provide `.env.example`; fail fast on missing config.
- Dependency pinning and `pip-audit`/`npm audit` in CI.
- Add an **acceptable-use layer**: configurable domain blocklist, optional robots.txt enforcement flag per org, Terms of Service and acceptable-use acceptance at signup, and abuse reporting (audit log of org, URL, time).

## RELIABILITY

- Retries with exponential backoff and jitter for transient errors; distinguish retryable and permanent failures with typed error codes (`TIMEOUT`, `DNS_FAILURE`, `BLOCKED_URL`, `SELECTOR_NOT_FOUND`, `QUOTA_EXCEEDED`, ...).
- Dead-letter handling, job cancellation endpoint, graceful worker shutdown that closes browser sessions.
- Concurrency limits per org and global; backpressure when the queue is long.
- Browser crash recovery and session reaper.
- Database migrations are forward-only and tested; zero-downtime friendly.
- Data retention job: purge results and artifacts per plan.

## API QUALITY

- Versioned (`/v1`), OpenAPI documented with realistic examples, consistent error envelope `{error: {code, message, details}}`, cursor pagination, request IDs in every response and log line.
- Generate a Python and a JavaScript client example in `docs/`.

## PROJECT LAYOUT

```
scrapeflow/
  apps/
    api/            FastAPI app (routers, schemas, services, deps)
    worker/         Celery tasks, Selenium runner, step engine
    web/            Next.js dashboard
  packages/         shared code if needed
  migrations/
  tests/            unit, integration, e2e
  deploy/           docker-compose.prod.yml, Caddyfile, grafana dashboards
  docs/             architecture, API guide, runbook, security notes
  .github/workflows/
```

## WORKING METHOD

1. Start by reading the existing `scrapeflow/` folder (a working FastAPI + Selenium MVP with SSRF guard, step engine, job store). Reuse what is good; refactor what does not fit the architecture above. Summarize your plan in 15 lines or fewer before coding.
2. Build in these phases, committing after each with a clear message. After each phase run lint, type-check, and tests, and show the results.
   - **Phase 1**: Repo structure, config, Docker compose (api, worker, postgres, redis, selenium grid), health/ready endpoints, CI.
   - **Phase 2**: Database models + migrations, orgs/users/API keys (hashed), auth, rate limiting.
   - **Phase 3**: Worker + Selenium Grid runner, scrape endpoint, SSRF/network isolation, typed errors, retries, artifact storage.
   - **Phase 4**: Automation step engine with the typed step union, secrets handling, failure screenshots.
   - **Phase 5**: Plans, credits, quotas, Stripe integration and webhooks.
   - **Phase 6**: Schedules, change detection, webhooks (signed), exports.
   - **Phase 7**: Proxy provider interface and rotation.
   - **Phase 8**: Dashboard.
   - **Phase 9**: Observability, load test script (k6 or Locust), security review pass, docs and runbook.
3. Write tests as you go, not at the end. Minimum: unit tests for the SSRF validator (include IPv6, redirects, decimal/octal IP tricks, DNS rebinding cases), step validation, quota logic, API key hashing, webhook signing; integration tests for the job lifecycle against real Postgres/Redis (testcontainers) and a local static test site served in the test suite for Selenium tests (never hit third-party sites in tests).
4. Never claim something works without running it. If Chrome/Docker is unavailable in your environment, say exactly which checks you could not run and give me the commands to run them.
5. Ask me a question only when a decision is both irreversible and genuinely ambiguous; otherwise choose the sensible default, note it in `docs/decisions.md`, and continue.
6. Keep functions small, typed, and documented where non-obvious. No dead code, no commented-out blocks, no placeholder keys.

## ACCEPTANCE CRITERIA

- `docker compose up` brings up the whole stack; a seeded demo org and API key are printed or documented.
- A scrape of a local test page returns correct title, text, links, selector data, and screenshot.
- An automation job (type, click, wait, extract) completes against the local test site; a failing step returns the log and a failure screenshot.
- Requests to `127.0.0.1`, `10.x`, `169.254.169.254`, and a redirect to an internal address are all rejected.
- Quota exhaustion returns 429/402 with correct headers; Stripe webhooks are idempotent.
- Killing a worker mid-job leaves no orphaned browser session after the reaper interval.
- CI is green: ruff, mypy, pytest, image builds.
- `docs/runbook.md` covers deploy, rollback, backups, scaling workers/nodes, and incident response.

## FINAL OUTPUT

When finished, give me: a summary of what was built per phase, how to run and deploy it, what was tested and what was not, known limitations, and a prioritized list of next improvements.

Start now with step 1.
