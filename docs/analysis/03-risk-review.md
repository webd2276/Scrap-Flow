# ScrapeFlow — Hostile Risk Review (baseline)

Every finding cites current code (`file:line`) and, where marked **[observed]**, was reproduced by a command in this environment. Severity reflects a multi-tenant SaaS that charges customers and runs untrusted URLs.

## Critical

### RISK-SEC-01 — SSRF is bypassable by redirect, DNS rebinding, and page JavaScript
**Evidence:** `security.py:22-37` resolves the host and returns the original URL; the browser resolves it again at `scraper.py:70` / `automation.py:57`. Redirects are validated only **after** `driver.get()` has already fetched the target (`scraper.py:71`, `automation.py:58`). No DNS pinning, no proxy, no Grid egress control (`Dockerfile:7-9`, `docker-compose.yml:1-9`). Webhook delivery uses `requests.post` (`jobs.py:57-61`) which follows redirects by default, validating only the first URL (`jobs.py:55`).
**Exploit:** attacker hosts `evil.example` → 302 to `http://169.254.169.254/latest/meta-data/` or `http://postgres:5432`; the browser fetches it, then the check fires too late. Page JS can fetch internal services directly regardless of URL checks. DNS rebinding (TTL 0, public→private) defeats the pre-check. Webhook redirect reaches internal HTTP services.
**Impact:** cloud metadata/credential theft, internal network recon, access to Postgres/Redis/admin planes.
**Fix:** app validation + connection-time validating egress proxy + pinned DNS/peer-IP check + redirect validation before each hop + webhook redirects disabled + isolated Grid network. Tests for IPv4/IPv6/octal/decimal/rebinding/redirect.
**Severity: Critical.**

### RISK-SEC-02 — No tenant isolation; any key can read any job
**Evidence:** one global plaintext key set (`config.py:12`, `main.py:19-24`); jobs carry no org (`jobs.py:24-32`); `GET /v1/jobs/{id}` returns any job (`main.py:82-87`). Keys are not scoped or revocable.
**Exploit:** a leaked customer key is a master key; a customer who learns/guesses another ID (IDs appear in webhooks/logs) reads another tenant's scrape results, including PII.
**Impact:** cross-tenant data breach; impossible to bill or audit per customer.
**Severity: Critical.**

### RISK-SEC-03 — Untrusted page JavaScript runs with Chrome sandbox disabled and no network isolation
**Evidence:** `--no-sandbox` (`scraper.py:25`), browser runs inside the API container (`scraper.py:36-37`), single compose network with no egress policy (`docker-compose.yml:1-9`), container capabilities not dropped, filesystem writable.
**Exploit:** malicious page exploits a Chrome renderer bug (sandbox absent) to reach the container/API/cloud metadata; or simply uses `fetch()` to attack internal services.
**Impact:** full API compromise from a customer-supplied URL.
**Severity: Critical.**

### RISK-SEC-04 — Webhooks are unsigned, unauthenticated, non-idempotent, and SSRF-capable
**Evidence:** `jobs.py:53-63` posts `{id,status,error}`, no HMAC/timestamp, no retries, swallows all failures, follows redirects.
**Exploit:** attacker subscribes a victim URL to generate traffic; forged callbacks cannot be distinguished by customers; replay is trivial; internal redirect via webhook.
**Impact:** customer trust/integrity, abuse traffic, internal SSRF.
**Severity: Critical.**

## High

### RISK-REL-01 — Jobs have no wall-clock timeout and can hang forever **[observed]**
**Evidence:** `scraper.py:38` sets only page-load timeout; `automation.py` has no total budget; `jobs.py:36-51` has no timeout. In the live run, a job stayed `running` for >60 s while Selenium Manager hung; it never transitioned.
**Impact:** threads/browsers pinned, queue starvation, cost blowup, false "running" forever.
**Severity: High.**

### RISK-REL-02 — No durable queue; restart loses all jobs
**Evidence:** in-memory dict + closures (`jobs.py:1`, `14-34`), single process. `Dockerfile:24` runs one worker; restart/redeploy wipes state; closures cannot be persisted.
**Impact:** lost customer work on every deploy/crash; cannot scale horizontally.
**Severity: High.**

### RISK-REL-03 — Orphaned Chrome processes and no reaper
**Evidence:** only `driver.quit()` in `finally` (`scraper.py:108-109`, `automation.py:125-126`); no session registry, no reaper. SIGKILL/crash leaves Chrome/driver processes; no Grid session cleanup.
**Impact:** memory exhaustion, eventually OOM-killed API.
**Severity: High.**

### RISK-REL-04 — Unbounded executor queue, no backpressure, no per-tenant concurrency
**Evidence:** `ThreadPoolExecutor(max_workers=3)` with default unbounded queue (`jobs.py:18`); no admission control; every POST is accepted.
**Impact:** traffic spike → memory growth/DoS; one tenant starves others.
**Severity: High.**

### RISK-REL-05 — TTL cleanup can delete running jobs and only runs on submit
**Evidence:** cleanup at `jobs.py:21`; cutoff `created_at` (`74-78`) without checking status; runs only on submit. A job older than `JOB_TTL_SECONDS` can be deleted mid-flight; idle processes never purge.
**Impact:** `_update` KeyError in worker, lost results, memory leak.
**Severity: High.**

### RISK-SEC-05 — Untyped automation input allows malformed/abusive payloads
**Evidence:** `main.py:39-41` accepts `list[dict[str, Any]]`; only step count checked (`main.py:72-73`). Selector strings, URLs, `seconds`, `y`, `timeout`, `text` are unbounded/free-form; `sleep` allows negative (`automation.py:92-93`); `wait_for timeout` converts arbitrary values (`89`).
**Exploit:** huge selector/text payloads, negative/NaN values, unknown keys, invalid actions reach the driver and produce 500-class job failures; no schema errors returned early.
**Severity: High.**

### RISK-SEC-06 — API keys are plaintext and never hashed
**Evidence:** `config.py:12` stores raw keys; `main.py:22` compares them. No prefix, org, scope, expiry, last-used, revocation. Missing keys return 503 rather than failing startup (`main.py:20-21`).
**Impact:** env/process leak exposes all customers; cannot rotate safely; violates spec.
**Severity: High.**

### RISK-SEC-07 — No rate limiting, quotas, or cost controls
**Evidence:** no Redis, no middleware, no metering anywhere (`main.py`).
**Impact:** a single key can saturate 3 browsers indefinitely; no 402/429; no revenue protection.
**Severity: High.**

### RISK-LEG-01 — PII extraction and scraping without acceptable-use controls
**Evidence:** `find_contacts` scrapes emails/phones (`scraper.py:100-102`); no robots.txt, domain blocklist, ToS acceptance, audit, or retention (`main.py`, `jobs.py`).
**Impact:** GDPR/CCPA and site-ToS violations; customer misuse attributed to the platform.
**Severity: High.**

### RISK-SEC-08 — Container hardening incomplete
**Evidence:** non-root (`Dockerfile:17-18`) is good, but no `read_only`, `cap_drop`, `security_opt`, `pids_limit`, or tmpfs; `--no-sandbox`; pip install as root; no image digest. `mem_limit`/`shm_size` only (`compose:7-9`).
**Severity: High.**

## Medium

### RISK-SEC-09 — SSRF validator crashes on invalid ports and has no length/host caps
**Evidence:** `security.py:23` passes `parsed.port`; `http://example.com:99999/` raises uncaught `ValueError` **[observed]**. No URL length/host length caps; no explicit IDNA normalization; no port allowlist (any port reaches internal services once IP checks are bypassed).
**Severity: Medium.**

### RISK-REL-06 — Webhook failures silently dropped; completion semantics unclear
**Evidence:** `jobs.py:62-63` swallows `UnsafeURL`/`RequestException`; no retries/DLQ; job marked done before delivery; payload excludes result.
**Impact:** customers miss events; no way to debug.
**Severity: Medium.**

### RISK-REL-07 — Unbounded memory from results held in RAM
**Evidence:** full text/HTML/base64 screenshot stored in the job dict (`scraper.py:103-106`, `jobs.py:24-32`); TTL 1 h; 3 concurrent; no size caps on screenshot or total result.
**Impact:** OOM under normal large-page use.
**Severity: Medium.**

### RISK-SEC-10 — Error strings leak internals
**Evidence:** `jobs.py:46` stores `type(exc).__name__ + str(exc)[:500]`; `automation.py:113` similar; webhook sends the error (`jobs.py:59`).
**Impact:** internal paths/hostnames/driver details exposed to tenants and webhook receivers.
**Severity: Medium.**

### RISK-COR-01 — Extraction semantics are incomplete/ambiguous
**Evidence:** CSS only (`scraper.py:48`); `extract` requires `rule["css"]`, so `xpath`/malformed rules raise `KeyError`; `all` defaults true (`51`); attributes may return `None`; no JSON-LD/OG/structured data; no pagination (`main.py:27-36`).
**Impact:** customers get wrong shapes/silent nulls; core product gaps.
**Severity: Medium.**

### RISK-COR-02 — Contact extraction is noisy
**Evidence:** email regex over full `page_source` (`scraper.py:101`); phone regex matches numeric noise, dates, IDs (`15-16`, `102`).
**Impact:** false leads, PII over-collection.
**Severity: Medium.**

### RISK-COR-03 — Automation semantics are thin
**Evidence:** no `hover`, `execute_if_present`, `loop_pages`, `retries` (`automation.py:54-108`); `press` only named `Keys` (`77-79`); `select` only by value (`86`); `sleep` not clamped low; `screenshot` viewport only (`55-56`); partial results use a dynamic attribute (`automation.py:123`).
**Severity: Medium.**

### RISK-OPS-01 — Observability is plain text, no request/job correlation
**Evidence:** `main.py:14` `basicConfig`; no middleware, metrics, tracing, Sentry, or job IDs in logs. `/health` only (`main.py:44-46`); no `/ready`, no dependency checks.
**Severity: Medium.**

### RISK-OPS-02 — No graceful shutdown or cancellation
**Evidence:** no signal handlers; `ThreadPoolExecutor` threads are non-daemon and cannot be cancelled; no cancel route. Deploy sends SIGTERM → in-flight Chrome/browser killed uncleanly.
**Severity: Medium.**

### RISK-SUP-01 — Supply chain and reproducibility weak
**Evidence:** wildcard versions (`requirements.txt:1-4`), no lock/hashes, unpinned base/chromium (`Dockerfile:1,7-9`), no audit in CI, Selenium Manager downloads driver/browser at runtime **[observed process]**, no SBOM.
**Severity: Medium.**

### RISK-DATA-01 — No persistence, migrations, retention, or backups
**Evidence:** no DB (`docker-compose.yml`), no Alembic, TTL in RAM (`jobs.py:74-78`); no object storage; no purge policy.
**Severity: Medium.**

### RISK-API-01 — API contract is not production grade
**Evidence:** error shape `{"detail":...}` **[observed]** (`main.py:53-54`), no error codes, no request IDs, no cursor pagination/list endpoints, no OpenAPI examples, no idempotency (`main.py`), no versioned error model.
**Severity: Medium.**

## Low

- **RISK-SEC-11** — `/health` reveals service liveness without auth (acceptable, but no rate limit). `main.py:44-46`.
- **RISK-SEC-12** — URL userinfo is accepted (`http://user:pass@host`) although it is not needed and can leak credentials into logs/results. `security.py:13-37`.
- **RISK-COR-04** — `wait_for` only checks presence, not visibility/stability (`scraper.py:72-75`); dynamic pages can be captured half-rendered.
- **RISK-OPS-03** — No CORS configuration; dashboard integration will fail or be opened too wide later (`main.py:16`).
- **RISK-LEG-02** — Proxy URL may contain credentials in env (`config.py:17`); not logged today, but no redaction layer exists.
- **RISK-DOC-01** — README claims features that are single-tenant/in-memory and warns about gaps (`README.md:65-71`); marketing/support mismatch risk.

## Attack-path summary

```mermaid
flowchart TD
    A[Attacker with any API key] --> B[Submit URL]
    B --> C{Pre-check passes?}
    C -->|public host| D[Chrome fetches]
    D --> E[302 / JS fetch to 169.254.169.254 or postgres:5432]
    E --> F[Internal data returned in result]
    C -->|rebind after check| D
    A --> G[Submit webhook to victim/internal URL]
    G --> H[Unsigned POST follows redirect]
    A --> I[Flood jobs]
    I --> J[Unbounded queue + 3 browsers + no timeout]
    J --> K[OOM / starvation]
    A --> L[Guess/observe job id]
    L --> M[Read another tenant's PII]
```

## What must be true before charging money

1. No browser in the API process; every job has a hard timeout, cancel path, and reaper.
2. Connection-time egress enforcement (proxy/pinned DNS/peer IP) plus isolated Grid network.
3. Tenant-scoped, hashed, scoped, revocable keys and per-org quotas/rate limits.
4. Signed, timestamped, retried, redirect-disabled webhooks.
5. Durable jobs/results, retention, migrations, and tenant-scoped reads.
6. Acceptable-use acceptance, domain blocklist, robots policy, and audit trail.
7. Observable: JSON logs with request/job IDs, metrics, readiness, Sentry.
