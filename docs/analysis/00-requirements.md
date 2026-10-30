# ScrapeFlow — Requirement Inventory

Source: `opencode_prompt_scrapeflow.md` (read in full). Code under analysis: `scrapeflow/` (512 lines of Python/config, no tests).
Priority: **MUST** = explicit requirement / acceptance criterion; **SHOULD** = strongly implied production quality; **NICE** = optional polish.

## 1. Product

| ID | Pri | Requirement |
|---|---|---|
| REQ-001 | MUST | Multi-tenant scraping + browser-automation API sold to marketing teams/agencies. |
| REQ-002 | MUST | Open a URL in a real browser (Selenium), extract data, and run scripted workflows (click, type, scroll, wait, extract, screenshot). |
| REQ-003 | MUST | REST API plus a small web dashboard. |
| REQ-004 | MUST | Support the named use cases: public lead/contact extraction, competitor price/content monitoring, SEO/meta audits, directory collection, scheduled recurring scrapes, and repetitive forms on customer-owned/authorized sites. |

## 2. Fixed stack

| ID | Pri | Requirement |
|---|---|---|
| REQ-005 | MUST | Python 3.12. |
| REQ-006 | MUST | FastAPI, Pydantic v2, SQLAlchemy 2.x async, Alembic. |
| REQ-007 | MUST | PostgreSQL 16 as system of record; Redis 7 for queue, rate limits, locks. |
| REQ-008 | MUST | Celery (or Arq) workers; Celery Beat for schedules. |
| REQ-009 | MUST | Selenium 4 with Selenium Grid standalone-chrome nodes. |
| REQ-010 | MUST | Docker + docker-compose (dev) and a production compose file; Caddy or Traefik TLS. |
| REQ-011 | MUST | Next.js App Router + TypeScript + Tailwind dashboard. |
| REQ-012 | MUST | Stripe subscriptions + metered usage. |
| REQ-013 | MUST | Structured JSON logs, Prometheus metrics, Sentry hooks, `/health` and `/ready`. |
| REQ-014 | MUST | pytest, pytest-asyncio, httpx, testcontainers; Playwright only for dashboard E2E. |
| REQ-015 | MUST | GitHub Actions: lint, type-check, test, build images. |
| REQ-016 | MUST | ruff, mypy strict on app code, pre-commit. |

## 3. Architecture and job semantics

| ID | Pri | Requirement |
|---|---|---|
| REQ-017 | MUST | API process never launches Chrome; workers talk to Selenium Grid. |
| REQ-018 | MUST | One browser session per job, always closed in `finally`; hard wall-clock job timeout; orphan-session reaper. |
| REQ-019 | MUST | Everything async from client view: `POST` returns 202 + `job_id`; results by `GET`, webhook, or export. |
| REQ-020 | MUST | `Idempotency-Key` header supported on job creation. |

## 4. Scrape endpoint

| ID | Pri | Requirement |
|---|---|---|
| REQ-021 | MUST | `POST /v1/scrape` accepts: `url`, `selectors` (CSS **or XPath**, with `attr`, `all`), `wait_for`, `render_js`, `screenshot`, `include_html`, `extract` (`links`, `meta`, `text`, `emails`, `phones`, `structured_data` JSON-LD/OpenGraph), `pagination` (next selector + max pages), `webhook_url`, `proxy_country`. |

## 5. Automation endpoint

| ID | Pri | Requirement |
|---|---|---|
| REQ-022 | MUST | `POST /v1/automate` takes an ordered step list validated by a discriminated Pydantic union; no free-form dicts. |
| REQ-023 | MUST | Actions: `goto, click, type, press, select, hover, wait_for, sleep, scroll, extract, get_text, screenshot, execute_if_present, loop_pages`. |
| REQ-024 | MUST | Per-step `optional`, `timeout`, `retries`. |
| REQ-025 | MUST | On failure return the step log plus a failure screenshot. |
| REQ-026 | MUST | Secrets via `secrets` map referenced as `{{secret.NAME}}`; never stored, never logged, redacted in responses. |

## 6. Schedules, change detection, exports

| ID | Pri | Requirement |
|---|---|---|
| REQ-027 | MUST | `POST /v1/schedules` for cron-style recurring jobs. |
| REQ-028 | MUST | Store schedule history, diff against previous result, fire webhook/email on watched-field changes (price changed, element appeared/disappeared). |
| REQ-029 | MUST | CSV and JSON export per job and per schedule history; streaming for large results. |

## 7. Accounts, keys, billing

| ID | Pri | Requirement |
|---|---|---|
| REQ-030 | MUST | Organizations, users, roles (owner/admin/member). |
| REQ-031 | MUST | API keys per org, hashed at rest (only hash + prefix), revocable, scoped, with last-used timestamps. |
| REQ-032 | MUST | JWT sessions for the dashboard. |
| REQ-033 | MUST | Plans Free/Starter/Pro/Business in config with monthly credits, max concurrent jobs, max steps, max pages, screenshot retention. |
| REQ-034 | MUST | Credit cost per job varies by features (JS rendering, screenshots, proxies). |
| REQ-035 | MUST | Atomic quota checks in Redis, reconciled to Postgres. |
| REQ-036 | MUST | Stripe checkout, customer portal, signature-verified idempotent webhooks. |
| REQ-037 | MUST | Clear 402/429 responses with `Retry-After` and remaining-quota headers. |

## 8. Proxies and dashboard

| ID | Pri | Requirement |
|---|---|---|
| REQ-038 | MUST | Pluggable proxy provider (static list, authenticated rotating gateway); per-job assignment, health checks, retry with a different proxy on connection failure. |
| REQ-039 | MUST | No CAPTCHA solving and no fingerprint-spoofing code. |
| REQ-040 | MUST | Dashboard pages: login/signup, API keys, scrape form + live JSON preview, automation step builder, job list/detail (status, logs, screenshot, result, export), schedules, usage/billing. |
| REQ-041 | MUST | Dashboard is fast/plain; Tailwind + small component set only. |

## 9. Security

| ID | Pri | Requirement |
|---|---|---|
| REQ-042 | MUST | SSRF defense for initial URL, every redirect, final URL and webhook URL; block private/loopback/link-local/metadata/reserved IPv4+IPv6; re-validate after redirects; pin DNS where possible. |
| REQ-043 | MUST | Selenium Grid on an isolated Docker network with egress rules blocking internal ranges at network level. |
| REQ-044 | MUST | Only `http`/`https`; block `file:`, `chrome:`, `javascript:`, `data:` navigation. |
| REQ-045 | MUST | Validate/cap URL length, step count, selector length, sleep seconds, response sizes, pages, screenshot size. |
| REQ-046 | MUST | API keys hashed SHA-256 with server-side pepper, constant-time compare, never logged. |
| REQ-047 | MUST | Per-org and per-IP rate limiting (Redis token bucket). |
| REQ-048 | MUST | Signed webhooks (`X-ScrapeFlow-Signature`) with timestamp replay prevention. |
| REQ-049 | MUST | Non-root containers, read-only filesystem where possible, dropped capabilities, resource limits, Chrome `shm_size`. |
| REQ-050 | MUST | Secrets only via env/secret manager; `.env.example`; fail fast on missing config. |
| REQ-051 | MUST | Dependency pinning and `pip-audit`/`npm audit` in CI. |
| REQ-052 | MUST | Acceptable-use layer: configurable domain blocklist, optional per-org robots.txt enforcement, ToS/acceptable-use acceptance at signup, abuse audit log (org, URL, time). |

## 10. Reliability and API quality

| ID | Pri | Requirement |
|---|---|---|
| REQ-053 | MUST | Retries with exponential backoff + jitter; typed errors (`TIMEOUT`, `DNS_FAILURE`, `BLOCKED_URL`, `SELECTOR_NOT_FOUND`, `QUOTA_EXCEEDED`, ...). |
| REQ-054 | MUST | Dead-letter handling, job cancel endpoint, graceful worker shutdown that closes browsers. |
| REQ-055 | MUST | Per-org and global concurrency limits; backpressure when the queue is long. |
| REQ-056 | MUST | Browser crash recovery and session reaper. |
| REQ-057 | MUST | Forward-only, tested migrations; zero-downtime friendly. |
| REQ-058 | MUST | Retention job purges results/artifacts per plan. |
| REQ-059 | MUST | Versioned `/v1`; OpenAPI with realistic examples; Python and JavaScript client examples in `docs/`. |
| REQ-060 | MUST | Consistent error envelope `{error:{code,message,details}}`. |
| REQ-061 | MUST | Cursor pagination. |
| REQ-062 | MUST | Request IDs in every response and every log line. |
| REQ-063 | MUST | Python + JavaScript client examples in `docs/`. |
| REQ-064 | MUST | Prescribed repo layout (`apps/api`, `apps/worker`, `apps/web`, `packages`, `migrations`, `tests`, `deploy`, `docs`, `.github/workflows`). |

## 11. Working method and acceptance

| ID | Pri | Requirement |
|---|---|---|
| REQ-065 | MUST | Read existing folder, reuse what is good, refactor what does not fit. |
| REQ-066 | MUST | Build in the 9 specified phases, commit after each, run lint/type/tests each phase. |
| REQ-067 | MUST | Tests as you go: SSRF (IPv6, redirects, decimal/octal, DNS rebinding), step validation, quota math, key hashing, webhook signing; integration with real Postgres/Redis; Selenium against a local static site only. |
| REQ-068 | MUST | Never claim unverified behavior; state unavailable checks and exact commands. |
| REQ-069 | MUST | Ask only irreversible+ambiguous questions; otherwise default and log in `docs/decisions.md`. |
| REQ-070 | MUST | Small typed functions, non-obvious code documented; no dead/commented/placeholder code. |
| REQ-071 | MUST | `docker compose up` brings up the full stack; seeded demo org + API key printed/documented. |
| REQ-072 | MUST | Local scrape returns correct title, text, links, selector data, screenshot. |
| REQ-073 | MUST | Local automation (type/click/wait/extract) completes; failing step returns log + failure screenshot. |
| REQ-074 | MUST | Reject `127.0.0.1`, `10.x`, `169.254.169.254`, and redirect-to-internal. |
| REQ-075 | MUST | Quota exhaustion returns 429/402 with correct headers; Stripe webhooks idempotent. |
| REQ-076 | MUST | Killing a worker mid-job leaves no orphaned browser after reaper interval. |
| REQ-077 | MUST | CI green: ruff, mypy, pytest, image builds. |
| REQ-078 | MUST | `docs/runbook.md` covers deploy, rollback, backup/restore, scaling, incident response. |
| REQ-079 | MUST | Final output: per-phase summary, how to run/deploy, tested vs. not, limitations, prioritized next steps. |

## 12. Ambiguities, contradictions, unstated assumptions

| # | Issue | Impact | Proposed resolution (default) |
|---|---|---|---|
| A-01 | Spec fixes Python 3.12, but this host only has 3.14; Docker image uses 3.12. | Local tooling drifts from prod. | Use `uv`-managed CPython 3.12.16 for all local verification; Docker stays `python:3.12-slim`. |
| A-02 | Spec fixes PostgreSQL 16; host runs PostgreSQL 18.6. | Local integration differs from prod. | Compose pins `postgres:16`; local integration tests tolerate 18 and record the difference. |
| A-03 | `render_js` is ambiguous when the product is browser-first. | Cost and semantics of `false`. | `true` = Selenium Grid browser; `false` = SSRF-safe HTTP fetch (no browser), documented. |
| A-04 | "Email when watched fields change" names no email provider. | Cannot ship a provider without credentials. | Webhook is always available; SMTP is optional via env, otherwise change event is recorded and email marked skipped. |
| A-05 | Plan limits/credit weights/retention are unspecified. | Quota math is arbitrary. | Define explicit defaults in config + `docs/decisions.md`; all configurable. |
| A-06 | `proxy_country` depends on provider capability. | Static proxy cannot honor country. | Provider interface exposes `supports_country`; request gets 422 `PROXY_COUNTRY_UNSUPPORTED` if not available, never silently ignored. |
| A-07 | "Optional robots.txt enforcement per org" can conflict with customer intent. | Legal/abuse exposure. | New orgs default `respect_robots=true`; disabling requires explicit ToS acceptance and is audited. |
| A-08 | Network-level egress blocking cannot be expressed portably in compose. | App checks are bypassable by page JS. | Ship an egress-validating proxy in front of Grid + documented host firewall/network policy; compose provides the proxy path. |
| A-09 | Stripe live checkout cannot be verified without account keys. | Acceptance item only partially testable. | Implement/test signature verification and idempotency with test secrets; live checkout marked UNVERIFIED with commands. |
| A-10 | `docker compose up` acceptance requires Docker, which this host denies to the current user. | Full-stack acceptance unverifiable here. | Implement compose; at checkpoint ask for Docker access or run commands as the user; report exactly what is unverified. |
| A-11 | Contact extraction (emails/phones) is PII collection. | GDPR/ToS exposure. | Keep feature but gate with acceptable-use acceptance, domain blocklist, audit log, and documented customer responsibility. |
| A-12 | Proxy rotation can look like evasion; spec forbids CAPTCHA/fingerprint evasion. | Legal/ethical boundary. | Proxies only for geo/rate/availability; no stealth/fingerprint code; document acceptable use. |
