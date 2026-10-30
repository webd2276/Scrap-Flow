# ScrapeFlow — System Map (as-is)

Analyzed 2026-10-30. Code under `scrapeflow/` is a 512-line MVP: 5 Python modules, one Dockerfile, one single-service compose file, no tests, no database, no queue, no dashboard, no CI. All line references are to the current tree.

## 1. Architecture as it exists today

```mermaid
flowchart LR
    C[Client] -->|X-API-Key| A[FastAPI process<br/>uvicorn, 1 worker]
    A -->|validate URL| S[SSRF guard<br/>getaddrinfo + ipaddress]
    A -->|submit closure| J[JobStore<br/>in-memory dict + ThreadPoolExecutor 3]
    J -->|thread calls| B[Selenium Chrome<br/>same container/process]
    B -->|navigate| I[(Internet)]
    J -->|best-effort POST| W[Webhook URL]
    A -->|poll| J
```

Everything runs in one Python process. There is no Postgres, Redis, Celery, Selenium Grid, dashboard, billing, schedules, or persistence. The API process itself launches Chrome from worker threads.

### Process / thread model
- `uvicorn ... --workers 1` (`scrapeflow/Dockerfile:24`); one API process.
- `JobStore` owns a `ThreadPoolExecutor(max_workers=config.MAX_WORKERS)` (`scrapeflow/app/jobs.py:14-18`), default 3 (`scrapeflow/app/config.py:27`).
- Each worker thread calls `make_driver()` directly (`scrapeflow/app/scraper.py:19-39`, `scrapeflow/app/automation.py:46`), so Chrome lives inside the API container.
- Jobs are submitted as in-process closures (`scrapeflow/app/main.py:55-66`, `70-78`); a restart loses every queued/running job.

### State
- All job state is a process-local dict guarded by a `threading.Lock` (`scrapeflow/app/jobs.py:16-17`, `24-32`).
- TTL cleanup runs only when a new job is submitted (`scrapeflow/app/jobs.py:20-21`, `74-78`), so an idle process retains jobs forever.
- No tenant/org identifier exists on a job, so any valid key can read any job by ID (`scrapeflow/app/main.py:82-87`).

### Data flow (scrape)
1. Request validated by `ScrapeRequest` (`main.py:27-36`); `HttpUrl` enforces http/https.
2. `assert_safe_url` resolves DNS and checks IP classes (`main.py:51-54`, `security.py:13-37`).
3. `store.submit` stores a job and schedules a thread (`jobs.py:20-34`).
4. Thread calls `scrape()` (`scraper.py:59-109`), which re-validates, launches Chrome, navigates, re-validates `driver.current_url` **after** the page has been fetched (`scraper.py:67-71`), extracts, and quits in `finally` (`scraper.py:108-109`).
5. Webhook fires after completion, unsigned, with only id/status/error (`jobs.py:50-63`).

### Data flow (automation)
1. `AutomateRequest.steps` is an untyped `list[dict[str, Any]]` (`main.py:39-41`).
2. `run_steps` loops over dicts and dispatches by `step["action"]` string (`automation.py:40-120`).
3. `goto` validates before navigation and again after (`automation.py:54-58`), same post-fetch weakness.
4. Failures return `partial` log/outputs via a dynamically attached attribute (`automation.py:112-124`).

## 2. Public API inventory

| Method | Path | Auth | Input | Output / status | Errors | Evidence |
|---|---|---|---|---|---|---|
| GET | `/health` | none | — | `{"status":"ok"}` 200 | — | `app/main.py:44-46` |
| GET | `/docs`, `/openapi.json` | none | — | FastAPI-generated spec | — | `app/main.py:16` |
| POST | `/v1/scrape` | `X-API-Key` | `url` (HttpUrl), `selectors` (untyped dict), `wait_for`, `screenshot`, `include_html`, `find_contacts`, `webhook_url` | 202 `{job_id,status_url}` | 400 unsafe URL; 401 bad/missing key; 503 no keys configured; 422 schema | `app/main.py:27-36`, `49-67`; `security.py:13-37` |
| POST | `/v1/automate` | `X-API-Key` | `steps: list[dict]`, `webhook_url` | 202 `{job_id,status_url}` | 400 too many steps; 401; 422 only for list/URL shape | `app/main.py:39-41`, `70-79` |
| GET | `/v1/jobs/{job_id}` | `X-API-Key` | path id | job object 200 | 404 unknown/expired | `app/main.py:82-87` |

Observed error shape is FastAPI's `{"detail": "..."}` (curl 400 in §5), not the required `{error:{code,message,details}}` envelope.

### Auth
- Keys come from a comma-separated `API_KEYS` env var (`config.py:12`), stored plaintext in memory.
- One global key list; no org, scope, revocation, prefix, last-used, or hash (`main.py:19-24`).
- Comparison uses `secrets.compare_digest` per key (`main.py:22`), which is constant-time per comparison but leaks list position via short-circuit iteration (`any(...)`), and keys remain plaintext.
- Missing `API_KEYS` does not fail startup; it returns 503 per request (`main.py:20-21`).

### Scrape capabilities present
- CSS selectors with `attr` and `all` (`scraper.py:42-52`), but no XPath.
- Title, body text (capped), links (capped), selected meta, optional email/phone regex, optional HTML, optional screenshot base64 (`scraper.py:77-106`).
- `wait_for` via CSS presence (`scraper.py:72-75`).
- No `render_js`, `extract` object, JSON-LD/OpenGraph structured data, pagination, or `proxy_country` (`main.py:27-36`).

### Automation capabilities present
- `goto, click, type, press, select, wait_for, sleep, scroll, extract, get_text, screenshot` (`automation.py:54-108`).
- `optional` is honored (`automation.py:114-115`); `timeout` only exists for `wait_for` (`automation.py:89`); no `retries`.
- Missing `hover`, `execute_if_present`, `loop_pages`, and the typed union.
- Failure screenshot is captured and swallowed if capture itself fails (`automation.py:116-119`).
- Secrets map / `{{secret.NAME}}` interpolation: absent.

## 3. Dependency inventory

| Dependency | Declared | Installed during analysis | Assessment |
|---|---|---|---|
| fastapi | `0.115.*` (`requirements.txt:1`) | 0.115.14 | Wildcard patch; no lock/hashes; upgrades silently. |
| uvicorn[standard] | `0.32.*` (`requirements.txt:2`) | 0.32.1 | Wildcard patch; pulls 12+ transitive packages (uvloop, watchfiles, websockets, wsproto...). |
| selenium | `4.25.*` (`requirements.txt:3`) | 4.25.0 | Wildcard patch; Selenium Manager auto-download at runtime (observed). |
| requests | `2.32.*` (`requirements.txt:4`) | 2.32.5 | Wildcard patch; webhook client; redirects followed by default. |
| Base image | `python:3.12-slim` (`Dockerfile:1`) | — | Not digest-pinned. |
| Browser | Debian `chromium`/`chromium-driver` (`Dockerfile:7-9`) | — | Unpinned version; browser/driver mismatch risk. |
| Transitives | none pinned | see §5 | Reproducibility and supply-chain risk. |

No lock file, no `pip-audit`, no `npm` project, no SBOM.

## 4. Deployment as-is

- `Dockerfile`: Debian slim + chromium + driver + tini; pip install requirements; copies `app/`; creates/uses user `scraper` (`Dockerfile:17-18`); healthcheck on `/health` (`Dockerfile:21`); one uvicorn worker (`Dockerfile:24`).
- Chrome runs with `--no-sandbox` inside the app container (`scraper.py:25`), so page JS is not contained by Chrome's sandbox.
- `docker-compose.yml`: one service (`scrapeflow`), host port 8000, `env_file: .env` (`docker-compose.yml:1-9`), `shm_size: 1gb`, `mem_limit: 2g`, restart policy. No Postgres/Redis/Grid/TLS/volumes.
- `.env` is absent from the tree (only `.env.example`), so `docker compose up` cannot start as shipped.
- No migrations, no CI, no runbook, no backups, no object storage.

## 5. Environment and execution evidence (2026-10-30)

Commands were run from the workspace; all observations are reproducible.

| Check | Result |
|---|---|
| Host Python | `Python 3.14.4`; no `python3.12` binary, no `ensurepip`, `pip` externally managed. |
| Isolated runtime | Installed `uv 0.13.6`; downloaded CPython 3.12.16; the first venv attempt failed (`ensurepip` missing), so the analysis venv at `/tmp/opencode/sf-venv` reports **Python 3.14.4**. Dependencies imported successfully there. |
| Docker | CLI `29.9.2`, Compose `v5.6.1`; daemon call fails: `permission denied ... /var/run/docker.sock`. User is not in `docker` group; `sudo -n` fails (password required). **Docker/Grid/testcontainers cannot run here.** |
| PostgreSQL | Server `18.6` active on 5432; peer auth; no application database/user. Spec target is 16. |
| Redis | Not installed; `redis-cli` missing. `apt-get download redis-server` succeeded (8.0.5 .deb), so a user-space binary can be extracted for local integration. |
| Chrome/chromedriver | Not installed. `https://googlechromelabs.github.io/.../last-known-good-versions-with-downloads.json` returned 200 (Stable 156.0.8078.80); Chrome for Testing zips are downloadable. |
| Node/npm | `v24.22.1` / `11.19.1`. |
| Java | OpenJDK `25.0.4` (could run Selenium Grid standalone jar). |
| Network | PyPI reachable (200); Chrome for Testing reachable; Ubuntu apt downloads work. |
| Git | Workspace is **not** a git repository; no commit history exists. |

### Existing app run
```text
$ API_KEYS=testkey uvicorn app.main:app --port 8123
GET  /health                              -> 200 {"status":"ok"}
POST /v1/scrape (no key)                  -> 401
POST /v1/scrape url=http://127.0.0.1:8123 -> 400 {"detail":"Target resolves to a non-public address"}
POST /v1/automate [{"action":"sleep",...}]-> 202 {"job_id":"c25f..."}
GET  /v1/jobs/c25f... (after 60s)         -> status:"running"   # never finished
```
While the job was "running", Selenium Manager was observed:
`/tmp/opencode/sf-venv/.../selenium-manager --browser chrome ...` — it hung for >60 seconds. The job had no wall-clock timeout, so it stayed `running` indefinitely. This is direct evidence for the missing job timeout/reaper (REQ-018, REQ-056).

### SSRF guard behavior (direct function calls)
```
BLOCKED  127.0.0.1, 10.0.0.1, 169.254.169.254, localhost
BLOCKED  2130706433, 0177.0.0.1, 0x7f000001        (numeric/octal/hex forms)
BLOCKED  [::1], [::ffff:127.0.0.1]
BLOCKED  file:///etc/passwd, javascript:alert(1)
BLOCKED  http://user:pass@127.0.0.1/
CRASH    http://example.com:99999/ -> ValueError: Port out of range 0-65535
```
The class-based checks are decent, but validation is **resolve-then-return** (`security.py:22-37`); the browser resolves the name again later, so DNS rebinding defeats it. Redirects are checked only **after** navigation (`scraper.py:70-71`, `automation.py:57-58`), and webhook redirects are never validated (`jobs.py:55-61`).

## 6. What is actually reusable

| Keep | Refactor / replace |
|---|---|
| IP-class deny logic in `security.py:28-36` | Wrap in a validator with pinning/proxy enforcement, redirect checks, port handling, typed errors. |
| `extract()` selector shape (`scraper.py:42-52`) | Extend to XPath, typed specs, caps; move to worker package. |
| Step action bodies (`automation.py:54-108`) | Replace dispatcher with discriminated union models; add secrets, retries, timeout, new actions. |
| Failure screenshot approach (`automation.py:116-120`) | Store artifact in object storage, return redacted reference. |
| Docker non-root/tini/shm intuition | Split API/worker/Grid, harden, add limits/read-only/caps. |
| README examples | Rewrite against the real API and client docs. |

Everything else (job store, auth, request models, compose, health, webhook) must be rebuilt to satisfy the spec.
