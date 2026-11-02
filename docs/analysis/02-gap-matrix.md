# ScrapeFlow — Gap Matrix (baseline)

Status: **Done** = meets requirement; **Partial** = some behavior exists; **Missing** = absent; **Wrong** = present but violates the requirement; **Unverified** = cannot test in this environment.

Evidence format `file:line`. Effort: S ≤ 0.5 day, M 1–2 days, L 3+ days. Risk = delivery/security risk if left as-is.

| REQ | Pri | Status | Evidence | What is needed | Effort | Risk |
|---|---|---|---|---|---|---|
| REQ-001 | MUST | Wrong | `app/config.py:12`, `app/main.py:19-24` | Orgs/tenants, per-org keys, tenant-scoped queries | L | H |
| REQ-002 | MUST | Partial | `app/scraper.py:19-109`, `app/automation.py:40-126` | Grid-based browser runner, full action set | M | H |
| REQ-003 | MUST | Partial | `app/main.py:44-87` | Dashboard (Next.js) + complete REST surface | L | M |
| REQ-004 | MUST | Missing | no schedules/audits/monitoring | Feature coverage via scrape/automate/schedules/monitoring | L | M |
| REQ-005 | MUST | Partial | host Python 3.14.4; `Dockerfile:1` 3.12 | Pin 3.12 locally/CI; keep image 3.12 | S | L |
| REQ-006 | MUST | Partial | FastAPI/Pydantic present (`requirements.txt:1-4`); no SQLAlchemy/Alembic | SQLAlchemy async, Alembic, Pydantic v2 schemas | L | H |
| REQ-007 | MUST | Missing | no PG/Redis in `docker-compose.yml:1-9` | Postgres 16 + Redis 7 services, DB layer, Redis client | L | H |
| REQ-008 | MUST | Missing | `jobs.py:1` explicitly in-process | Celery worker + beat, durable broker | L | H |
| REQ-009 | MUST | Missing | `scraper.py:36-37` launches local Chrome | Selenium Grid nodes; remote webdriver | M | H |
| REQ-010 | MUST | Partial | `docker-compose.yml:1-9` one service; no prod/TLS | Dev/prod compose, Caddy/Traefik | M | M |
| REQ-011 | MUST | Missing | no `apps/web` | Next.js App Router + TS + Tailwind | L | M |
| REQ-012 | MUST | Missing | no Stripe code | Checkout/portal/webhooks/metering | L | H |
| REQ-013 | MUST | Partial | `main.py:14` plain logging; `main.py:44-46` health | JSON logs, Prometheus, Sentry, readiness | M | M |
| REQ-014 | MUST | Missing | no tests/tooling | pytest stack + testcontainers + local site | L | H |
| REQ-015 | MUST | Missing | no `.github` | CI workflow: lint/type/test/audit/build | M | M |
| REQ-016 | MUST | Missing | no ruff/mypy/pre-commit config | Tooling config + strict apps | S | M |
| REQ-017 | MUST | Wrong | `scraper.py:19-39`, `automation.py:46` API process launches Chrome | Move execution to worker + Grid | M | H |
| REQ-018 | MUST | Partial | `scraper.py:108-109` finally quit; no timeout/reaper | Hard timeout, watchdog, reaper, cancel | L | H |
| REQ-019 | MUST | Partial | `main.py:49-79` 202; `jobs.py:14-34` in memory | Durable job row + queue + result access | L | H |
| REQ-020 | MUST | Missing | no header handling | Idempotency table + replay of stored response | M | M |
| REQ-021 | MUST | Partial | `main.py:27-36`, `scraper.py:42-106` | render_js, XPath, extract object, JSON-LD/OG, pagination, proxy_country | L | H |
| REQ-022 | MUST | Wrong | `main.py:39-41` free-form dict; `automation.py:34-38` | Discriminated Pydantic union + validation | M | H |
| REQ-023 | MUST | Partial | `automation.py:54-108` missing hover/execute_if_present/loop_pages | Implement 3 actions | M | M |
| REQ-024 | MUST | Partial | `automation.py:114-115` optional only; timeout only `wait_for` | Per-step timeout/retries | M | M |
| REQ-025 | MUST | Partial | `automation.py:112-120` log + screenshot; capture swallowed | Guaranteed artifact + redacted log | S | M |
| REQ-026 | MUST | Missing | no secrets handling | Secret map, interpolation, redaction, no persistence | M | H |
| REQ-027 | MUST | Missing | no routes | Schedule model/API + beat dispatcher | L | M |
| REQ-028 | MUST | Missing | no history/diff | Snapshot history, diff, notifications | L | M |
| REQ-029 | MUST | Missing | no export routes | Streaming CSV/JSON job + schedule exports | M | M |
| REQ-030 | MUST | Missing | single key list `config.py:12` | Org/user/role models + membership | L | H |
| REQ-031 | MUST | Wrong | plaintext keys `config.py:12`, `main.py:22` | Hash+pepper, prefix, scopes, revoke, last-used | M | H |
| REQ-032 | MUST | Missing | no JWT/login | Auth service + JWT + password hashing | M | H |
| REQ-033 | MUST | Missing | no plans | Config-driven plan catalog | S | M |
| REQ-034 | MUST | Missing | no credit logic | Feature-weighted credit calculator | S | M |
| REQ-035 | MUST | Missing | no Redis/quota | Atomic Lua reserve + reconcile job | L | H |
| REQ-036 | MUST | Missing | no Stripe | Billing integration + verified idempotent webhooks | L | H |
| REQ-037 | MUST | Missing | no 402/429 handling | Error mapping + headers | S | M |
| REQ-038 | MUST | Partial | `config.py:17`, `scraper.py:33-34` static single proxy | Provider interface, rotation, health, retry | M | M |
| REQ-039 | MUST | Done | no CAPTCHA/fingerprint code present | Keep out; enforce in review | — | L |
| REQ-040 | MUST | Missing | no frontend | All listed pages | L | M |
| REQ-041 | MUST | Missing | no frontend | Tailwind small component set | S | L |
| REQ-042 | MUST | Partial | `security.py:13-37`; post-fetch checks `scraper.py:70-71`, `automation.py:57-58`; webhook `jobs.py:55` | Pinning/egress proxy, pre-connect redirect validation, webhook redirect control | L | H |
| REQ-043 | MUST | Missing | single-container compose | Isolated Grid network + egress rules/proxy | M | H |
| REQ-044 | MUST | Done | `security.py:15`; verified blocks `file:`/`javascript:` | Keep; add browser-level navigation guard | S | M |
| REQ-045 | MUST | Partial | steps/sleep/links/text caps `config.py:25-32`; no URL/selector/pages/screenshot caps | Full input/response caps | S | M |
| REQ-046 | MUST | Wrong | plaintext `config.py:12`; constant-time per key `main.py:22` | SHA-256+pepper, prefix, no logs | M | H |
| REQ-047 | MUST | Missing | no rate limit | Redis token bucket per org/IP | M | H |
| REQ-048 | MUST | Missing | unsigned `jobs.py:53-63` | HMAC + timestamp + replay window + retries | M | H |
| REQ-049 | MUST | Partial | non-root `Dockerfile:17-18`; shm/mem `compose:7-9`; no read-only/caps | Harden all services, limits, read-only, cap_drop | M | M |
| REQ-050 | MUST | Partial | `.env.example` exists; no startup fail-fast; 503 at request `main.py:20-21` | Pydantic settings, fail-fast, secret handling | S | M |
| REQ-051 | MUST | Partial | wildcard pins `requirements.txt:1-4`; no audit | Lock file, hashes, pip-audit/npm audit | S | M |
| REQ-052 | MUST | Missing | no ToS/robots/blocklist/audit | AUP layer + audit log | M | H |
| REQ-053 | MUST | Missing | string exceptions `jobs.py:46`, `automation.py:120` | Typed error enum + retry policy + backoff | M | H |
| REQ-054 | MUST | Missing | no cancel/DLQ; finally only `scraper.py:108` | Cancel endpoint, DLQ, graceful shutdown | M | H |
| REQ-055 | MUST | Partial | global pool 3 `jobs.py:18`; unbounded executor queue | Per-org/global semaphores + backpressure | M | H |
| REQ-056 | MUST | Missing | no reaper; observed job stuck >60s | Session registry + reaper task | M | H |
| REQ-057 | MUST | Missing | no DB/migrations | Alembic forward-only + tests | M | M |
| REQ-058 | MUST | Partial | TTL purge on submit only `jobs.py:74-78` | DB retention worker per plan | S | M |
| REQ-059 | MUST | Missing | FastAPI spec at `main.py:16`, no examples | OpenAPI examples + versioning | S | L |
| REQ-060 | MUST | Wrong | observed `{"detail":...}` from `main.py:53-54` | Exception handlers + envelope | S | M |
| REQ-061 | MUST | Missing | only single job GET `main.py:82-87` | List endpoints with cursors | M | M |
| REQ-062 | MUST | Missing | no middleware | Request-ID middleware + log binding | S | L |
| REQ-063 | MUST | Missing | none | Python/JS examples in `docs/` | S | L |
| REQ-064 | MUST | Wrong | flat `app/` layout | Restructure per spec | M | M |
| REQ-065 | MUST | Done | this analysis | Continue reuse/refactor | — | L |
| REQ-066 | MUST | Partial | no git repo; no phase gates yet | Init repo, commit per phase, run gates | S | M |
| REQ-067 | MUST | Missing | zero tests | Full test pyramid with listed cases | L | H |
| REQ-068 | MUST | Done | analysis records environment limits | Keep reporting UNVERIFIED items | — | L |
| REQ-069 | MUST | Missing | no `docs/decisions.md` | Create and maintain | S | L |
| REQ-070 | MUST | Partial | no TODOs; `pass` in exception classes/swallowed capture (`security.py:10`, `automation.py:31,119`) | Typed code, no swallowed errors, docs | S | L |
| REQ-071 | MUST | Wrong | single service `compose:1-9`; no `.env`; no demo seed | Full compose + seed + printed key | L | H |
| REQ-072 | MUST | Unverified | no Chrome; no local site | Selenium test vs local static site | M | H |
| REQ-073 | MUST | Unverified | no Chrome; no local site | Automation e2e + failure screenshot test | M | H |
| REQ-074 | MUST | Partial | function blocks targets (verified); redirect fetched before check `scraper.py:70-71` | End-to-end reject incl. redirect | M | H |
| REQ-075 | MUST | Missing | no quota/Stripe | Quota tests + Stripe idempotency tests | M | H |
| REQ-076 | MUST | Missing | no reaper | Kill-worker test + reaper | M | H |
| REQ-077 | MUST | Missing | no CI | Green workflow incl. image build | M | M |
| REQ-078 | MUST | Missing | no runbook | Full runbook | S | M |
| REQ-079 | MUST | Missing | this is Phase 0 | Final report at end | S | L |

## Roll-up

- **Done:** 3 (REQ-039, 044, 065, 068 — note REQ-044 is done at app level only).
- **Partial:** 25.
- **Wrong:** 9.
- **Missing:** 40.
- **Unverified:** 2.

Critical-path gaps: durable job model/queue (REQ-007/008/018/019), worker/Grid split (REQ-009/017), SSRF depth (REQ-042/043), tenant auth (REQ-030/031), typed automation (REQ-022/024/026), quota (REQ-035/037), and tests/CI (REQ-014/067/077).

## Live delta after Phase 1–2 (2026-11-01)

This table supersedes the baseline row for the listed requirements. Remaining
baseline rows are unchanged and still describe unimplemented phases.

| REQ | Status | Live evidence |
|---|---|---|
| REQ-005 | Done | `pyproject.toml:6` requires `>=3.12,<3.13`; `Dockerfile:1`; CI uses Python 3.12. Local venv is CPython 3.12.16. |
| REQ-007 | Partial | `packages/core/db.py:29-45`, `packages/core/redis.py:10-25`, compose Postgres 16/Redis 7. Verified locally on PostgreSQL 18.6/Redis 8.0.5; compose run UNVERIFIED (Docker denied). |
| REQ-013 | Partial | JSON logs `packages/core/logging.py:10-29`; `/health` + `/ready` `apps/api/routers/health.py:13-37`; Sentry init `apps/api/main.py:34-41`. Prometheus endpoint is Phase 9. |
| REQ-014 | Partial | Unit + real PG/Redis integration suite in `tests/`; Selenium/local-site tests arrive with Phase 3. |
| REQ-015 | Partial | `.github/workflows/ci.yml` defines lint/type/unit/integration/audit/image jobs. Not executed on GitHub from this host. |
| REQ-030 | Done | `packages/core/models.py:64-142`; tenant resolution in `apps/api/deps.py:118-176`; isolation test `tests/integration/test_auth.py`. |
| REQ-031 | Done | `packages/core/security/keys.py:1-55`, `apps/api/services/keys.py:17-74`, `apps/api/deps.py:70-115`; hash/prefix/scope/revoke/last-used verified. |
| REQ-032 | Done | `packages/core/security/passwords.py`, `packages/core/security/tokens.py:41-110`, `apps/api/services/auth.py:47-206`, `apps/api/routers/auth.py:58-180`. |
| REQ-046 | Done | SHA-256 + pepper, prefix lookup, constant-time compare: `packages/core/security/keys.py:24-55`; plaintext never listed: `tests/integration/test_auth.py`. |
| REQ-047 | Done | Atomic Redis token bucket `packages/core/rate_limit.py:13-105`; org/IP/auth limits `apps/api/deps.py:178-245`; 429 + headers verified against real Redis. |
| REQ-050 | Done | `packages/core/settings.py:18-162`; missing/short secrets abort startup (verified). |
| REQ-051 | Done | `uv.lock`; `pip-audit` reports no known vulnerabilities (2026-11-01); CI audit job present. |
| REQ-052 | Partial | ToS acceptance/version recorded (`apps/api/services/auth.py:60-83`), append-only `audit_logs` (`packages/core/models.py:163-179`), audit writes on signup/login/key events. Robots/AUP enforcement is Phase 3. |
| REQ-057 | Done | `migrations/versions/f141298caa34_phase_2_tenancy_auth_keys_audit.py`; upgrade, `alembic check`, downgrade-to-base, and re-upgrade verified on a disposable DB (`tests/integration/test_migrations.py`). |
| REQ-060 | Done | Error envelope + typed codes `packages/core/errors.py`, handlers `apps/api/errors.py`. |
| REQ-062 | Done | `apps/api/middleware/request_context.py`; request IDs echoed and bound to JSON logs (verified live). |
| REQ-064 | Done | `apps/` + `packages/` layout; legacy `app/` removed in commit `8e7018f`. |
| REQ-066 | Done | Git repo; phase commits `0b5963f`, `8e7018f`; quality gates run per phase. |
| REQ-067 | Partial | 40 tests: 25 unit + 15 integration, 83.65% combined coverage. Browser/e2e layers pending. |
| REQ-069 | Done | `docs/decisions.md` D-001…D-018. |
| REQ-071 | Partial | Dev/prod compose, one-shot `migrate` service, seeded demo org/user/key (`scripts/seed.py`). Full compose/Grid startup UNVERIFIED (Docker denied). |
| REQ-077 | Partial | CI workflow defined but never executed on GitHub; `docker build` UNVERIFIED. |

Phase 2 explicit gaps carried forward:
- `usage_ledger` is intentionally deferred to Phase 5 with quota accounting.
- Role management/invite endpoints are not exposed yet; roles exist and are enforced.
- Prometheus `/metrics`, Stripe, Selenium, schedules, webhooks, retention remain later phases.

## Live delta after Phase 3 (2026-11-01)

Phase 3 adds the durable scrape path. "Done" below means exercised by tests or a
live process; browser/Grid items stay **Unverified** because Docker and Chrome
are unavailable on this host.

| REQ | Status | Live evidence |
|---|---|---|
| REQ-002 | Partial | HTTP scrape + pagination + CSS/XPath/attr/limits `apps/worker/scrape.py:294`, `apps/worker/extract.py`; Selenium runner `apps/worker/browser/runner.py`. Real browser UNVERIFIED (no Chrome/Grid). |
| REQ-008 | Done | Celery task + beat reaper `apps/worker/celery_app.py`, `apps/worker/tasks/jobs.py:30`, `apps/worker/tasks/reaper.py:69`; live API→Redis→worker run succeeded 2026-11-01. |
| REQ-009 | Partial | Remote webdriver only, proxy forced `apps/worker/browser/driver.py`; Grid service in compose. Real Grid session UNVERIFIED (Docker denied). |
| REQ-014 | Done | 130 tests + 1 explicit browser skip, 78.68% coverage; live E2E scrape completed. |
| REQ-017 | Done | API imports no Selenium/browser code; execution only in `apps/worker`. Dispatch boundary `apps/api/services/dispatch.py`. |
| REQ-018 | Done | Deadline checks `apps/worker/scrape.py`, soft/hard limits `apps/worker/tasks/jobs.py:170`, watchdog `apps/worker/browser/driver.py`, lease reaper `apps/worker/tasks/reaper.py:69`; cancel polled per redirect/chunk. |
| REQ-019 | Done | Durable `jobs`/`job_events`/`artifacts` `packages/core/models.py:226-303`; API `apps/api/routers/scrape.py:44`, `apps/api/routers/jobs.py:30-99`; migration round-trip verified. |
| REQ-020 | Done | `(org_id, idempotency_key)` unique + replay semantics `apps/api/services/jobs.py:31`; integration test asserts 200 + `Idempotent-Replay`. |
| REQ-021 | Partial | `render_js`, `wait_for`, screenshot, include_html, pagination, extract options `apps/api/schemas/scrape.py`. `proxy_country` intentionally rejected (422); webhook only validated, delivery is Phase 8. |
| REQ-022 | Partial | Discriminated scrape schema done; automation step union is Phase 4. |
| REQ-025 | Done | Result/HTML/screenshot artifacts with SHA-256 `apps/worker/scrape.py:106`, `packages/core/artifacts.py`; download headers verified live. |
| REQ-042 | Done | API pre-validation + connection-time pinned proxy `packages/core/ssrf.py:99-205`, `apps/worker/egress_proxy.py:66`; per-hop redirects `apps/worker/http_fetch.py`; browser final URL revalidated. Live public fetch succeeded; private destination returned 403. |
| REQ-043 | Partial | Compose adds internal `egress-proxy` and Selenium with no direct ingress; Grid/proxy containers UNVERIFIED (Docker denied). |
| REQ-045 | Partial | URL/selector/header/page/text caps in schema + worker; response byte cap `apps/worker/http_fetch.py`; screenshot pixel cap not yet enforced. |
| REQ-049 | Partial | All backend services read-only, `cap_drop: ALL`, `no-new-privileges`, tmpfs, mem/cpu limits; image build UNVERIFIED. |
| REQ-057 | Done | Phase 3 revision `b93c4fa40230`; upgrade→check→downgrade base→re-upgrade verified on a disposable DB (`tests/integration/test_migrations.py`). |
| REQ-067 | Done | 130 passed, 1 skipped (Chrome/Grid), 78.68% branch coverage. |
| REQ-071 | Partial | `egress-proxy`, MinIO + bucket initializer, queue selection, Grid in dev/prod compose; `docker compose config` renders for both. Startup UNVERIFIED (Docker denied). |

Phase 3 explicit gaps carried forward:
- Real Selenium Grid + Chrome rendering/screenshot is UNVERIFIED on this host.
- S3/MinIO upload, presign redirect, and bucket lifecycle are UNVERIFIED (no Docker/MinIO).
- Webhook delivery/signing, robots.txt enforcement, AUP domain blocklist, quotas,
  schedules, exports, and automation steps remain later phases.
- `proxy_country` remains a 422 until a proxy provider is configured.

## Live delta after Phase 4 (2026-11-02)

Phase 4 adds the typed automation engine. Browser execution is still
**Unverified** on this host; step semantics, secret handling, and the
API→worker lifecycle are exercised with fakes and integration tests.

| REQ | Status | Live evidence |
|---|---|---|
| REQ-002 | Partial | Scrape path complete; automation union/executor `apps/api/schemas/automation.py`, `apps/worker/browser/steps.py`. Real local Chrome run passed every action; Grid still UNVERIFIED. |
| REQ-022 | Done | Discriminated `action` union rejects unknown actions, missing fields, and extras `apps/api/schemas/automation.py:38-215`; tests cover every action. |
| REQ-023 | Done | `hover`, `execute_if_present`, and `loop_pages` implemented `apps/worker/browser/steps.py:337-374`; fake-browser unit tests. |
| REQ-024 | Done | Per-step `timeout_s`, `retries`, `optional`, and deadline checks `apps/worker/browser/steps.py:398-455`; retry/optional tests. |
| REQ-025 | Done | Result/HTML/step/failure screenshots with SHA-256 `apps/worker/automate.py:45-118`; failure returns partial result. |
| REQ-026 | Done | Declared-secret validation + `{{name}}` interpolation only in type/select/press `apps/api/schemas/automation.py:290-340`; AES-GCM Redis staging `packages/core/secretbox.py`, `apps/api/services/secrets.py`, worker deletion `apps/worker/secrets.py`. Integration asserts plaintext never reaches PostgreSQL. |
| REQ-045 | Partial | Step/secret/nesting/selector/text caps in the schema; response and screenshot byte/pixel caps still partial. |
| REQ-054 | Partial | Cancellation checked before automation and after execution; browser steps are not polled mid-step. |
| REQ-067 | Done | 167 passed, 1 skipped (Grid-specific), 78.18% branch coverage. |
| REQ-072 | Done | `tests/e2e/test_automation_browser.py` passed against Chrome for Testing 156 + chromedriver with a local static site: 7 actions, secret interpolation, and a failure screenshot. Grid/proxy compose still UNVERIFIED. |

Phase 4 explicit gaps carried forward:
- Real local Chrome execution is verified; Selenium Grid + egress-proxy compose execution is UNVERIFIED.
- Mid-step cancellation for browser jobs is checked between jobs/steps, not inside a blocking Selenium call.
- Screenshot pixel/byte caps and step-level plan limits arrive with Phase 5 plans.
