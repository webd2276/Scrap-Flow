Build a production-grade documentation & landing website for an open-source project called "ScrapeFlow" (GitHub: https://github.com/webd2276/Scrap-Flow). The site explains the project, presents a complete installation/setup guide (modelled exactly on the project's SETUP.md), and lets visitors preview a 37-page presentation PDF in the browser.

## TECH STACK
- Vite + React 18 + TypeScript + Tailwind CSS. Fully static, no backend, no database.
- lucide-react icons. react-pdf (pdfjs-dist) for the PDF viewer.
- Single page with anchor sections, smooth scroll, sticky navbar with active-section highlighting (IntersectionObserver). No React Router.
- Strictly typed, small components (src/components, src/data, src/lib). No unused code, no console errors. `npm run build` must pass with zero TS errors.

## DESIGN
- Dark theme default (navy #0b1020, indigo→cyan gradient accents) with light/dark toggle persisted in localStorage.
- Inter for text, JetBrains Mono for code. Rounded cards, subtle borders, soft glows, fade-in-on-scroll (respect prefers-reduced-motion).
- Mobile-first responsive (360 / 768 / 1280). Hamburger drawer on mobile.
- WCAG AA contrast, visible focus rings, semantic HTML, aria-labels, skip-to-content link.

## SECTIONS (in order)

1. **Navbar** (sticky, blurred): logo "SF ScrapeFlow"; links: Overview, Features, Architecture, Tech Stack, Setup, Presentation, Verified Scope; theme toggle; GitHub button.

2. **Hero**: title "ScrapeFlow"; subtitle "A production-shaped, multi-tenant web scraping & browser-automation platform: durable job queue, real headless browser path, SSRF-safe egress, tenant isolation and artifact storage." Chips: Python 3.12, FastAPI, Celery + Redis, PostgreSQL 16, Selenium Grid, S3 artifacts, Next.js 16, React 19, TypeScript. CTAs: "Get Started" (scroll to Setup), "View on GitHub". Animated count-up stat cards: 11 services in dev, 29 API routes, 322 tests passing, 15 DB models, 83.08% coverage. Decorative terminal card: `$ ./scripts/run.sh` then "✔ API ready · dashboard up".

3. **Overview**: four "reality" cards (real browser needed; long jobs cannot live in a request; user URLs are an attack surface (SSRF, DNS rebinding); multi-tenancy is not optional). Solution line: "One control plane. One queue. One dashboard. The API returns 202 Accepted and slow work runs in isolated workers."

4. **Features** (8 cards): Scrape API; Browser Automation (goto, click, type, wait, extract, screenshot); Schedules (cron, run history, manual trigger); Artifacts (presigned downloads, SHA-256, retention by plan); Signed Webhooks (HMAC, durable outbox, retries); Tenancy & Quotas; Billing (Stripe, plan quotas, off by default); Observability (JSON logs with request/job IDs, Prometheus, Sentry, /health, /ready).

5. **Architecture**: inline SVG/CSS diagram, 5 layers: Clients (Next.js dashboard, API consumers, Celery Beat) → Control plane (Next.js same-origin BFF, FastAPI that never launches Chrome) → Durable state (PostgreSQL 16, Redis 7, S3/MinIO) → Async execution (Celery worker, Celery Beat) → Egress (httpx + parsel, Selenium Grid, validating egress proxy with IP pinning). Below: 9-step "Request lifecycle" stepper (Authenticate → Validate → SSRF pre-check & quota → Persist & enqueue (202) → Execute → Extract → Store artifacts → Finalise → Consume).

6. **Tech Stack**: tabs Backend / Frontend / Infra with layer, technology, version, role. Backend: FastAPI 0.162, Starlette 1.10, Uvicorn 0.32, Pydantic v2, SQLAlchemy 2 async, asyncpg 0.30, Alembic 1.14, PostgreSQL 16, Celery 5.4, redis-py 5.2, croniter 3.0, httpx 0.27, parsel 1.9, Selenium 4.25, boto3, PyJWT 2.9, argon2-cffi, cryptography, structlog, prometheus-client, sentry-sdk, Stripe. Frontend: Next.js 16.4.5, React 19.3.1, TypeScript 5.9.3, Tailwind CSS 4.3.4, ESLint 9, Vitest, Playwright. Infra: Docker Compose v2, Caddy 2.8, Bash, PowerShell. Package managers: uv (Python), npm (Node 22).

7. **Setup & Installation Guide** (most important; use a left sticky sub-navigation on desktop listing its sub-sections, and a collapsible list on mobile). Content must follow SETUP.md exactly:

   **7.0 Overview note**: "Repository layout: the Git repository root contains `scrapeflow/`, `docs/`, `SETUP.md`, and `.github/`. Run application commands from `scrapeflow/` unless a step says otherwise."

   **7.1 Prerequisites**: two tables.
   - Docker setup: Docker Engine 24+ (Linux) / Docker Desktop (macOS, Windows); Docker Compose v2; Git; Bash 3.2+ (needed by run.sh; not needed for run.ps1); PowerShell 5.1+ (required for run.ps1); curl (needed by run.sh; not by run.ps1); jq (optional); ~10 GB disk; 8 GB RAM recommended.
   - Local dev/tests only: Python 3.12, uv 0.13+, Node.js 22+, npm 10+ (each with its version-check command).
   - Platform notes: Windows native uses scripts\run.ps1 or scripts\run.cmd (Docker Desktop + PowerShell only). Windows WSL 2/Git Bash uses ./scripts/run.sh (Docker Desktop WSL integration enabled). macOS uses ./scripts/run-macos.sh; python3 only needed to create .env or run fix-db-password (`xcode-select --install` or `brew install python`).

   **7.2 Get the project**: `git clone https://github.com/webd2276/Scrap-Flow.git web-scrapping-tool` then `cd web-scrapping-tool/scrapeflow` (Windows: `cd web-scrapping-tool\scrapeflow`). Note that all later commands run from inside `scrapeflow/`.

   **7.3 Fastest start, one command**: OS tabs (Linux | macOS | Windows PowerShell | Windows CMD) with copy buttons:
   - Linux `./scripts/run.sh`
   - macOS `./scripts/run-macos.sh`
   - Windows PowerShell `powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1`
   - Windows CMD `scripts\run.cmd`
   Show a "What the runner does" numbered list: 1 check Docker + Compose v2 (and curl on Linux/macOS); 2 create .env with random secrets if missing; 3 try the pinned MinIO image, fall back to adobe/s3mock if it cannot be pulled; 4 build and start postgres, redis, minio, migrate, minio-init, api, worker, beat, egress-proxy, selenium, web; 5 wait for http://127.0.0.1:8000/ready; 6 print URLs.
   Runner commands table (Linux/macOS vs Windows PowerShell): start/update, status, logs, seed, fix-db-password, stop (keep data), reset (stop and delete data, destructive).
   Sub-blocks: execution policy workaround (`scripts\run.cmd` or `powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1`); forcing storage mode (`SF_S3_MODE=s3mock|minio` for bash, `$env:SF_S3_MODE = 's3mock'` for PowerShell, `set SF_S3_MODE=s3mock` for CMD); slow machine timeout (`SF_HEALTH_TIMEOUT=420`).
   A visible callout "Verification scope": Linux runner and macOS wrapper exercised on Linux; run.ps1 exercised with PowerShell 7.4.6 on Linux; native Windows PowerShell 5.1 and native macOS NOT verified.
   URL table: Dashboard http://127.0.0.1:3000, API http://127.0.0.1:8000, API docs (development only) /docs, API metrics /metrics, Selenium Grid http://127.0.0.1:4444/status, MinIO console (when using MinIO) http://127.0.0.1:9001.

   **7.4 Manual Docker setup**: 4.1 create .env (`python3 scripts/generate_env.py`; Windows `py -3 scripts\generate_env.py`; mode 600 / restricted NTFS ACL; refuses to overwrite; never commit .env; review command with secrets redacted, bash and PowerShell versions). 4.2 `docker compose --project-directory . --env-file .env up -d --build`, plus the adobe/s3mock override file (YAML) and the command using `-f docker-compose.yml -f /tmp/sf-compose-override.yml`. Note migrations run automatically via the one-shot migrate service. 4.3 optional demo data `docker compose exec api python -m scripts.seed` (idempotent; creates org demo, user demo@example.com, admin-scoped API key printed once; password printed only on first creation).

   **7.5 Verify the stack**: curl commands for /health, /ready, dashboard /login status code, /metrics (bash) and the `curl.exe` PowerShell variants; expected outputs list; container status command.

   **7.6 First account & first scrape**: Dashboard route (/signup, accept ToS, submit URL + selectors; refresh token in httpOnly cookie, access token in memory). API with curl: signup → TOKEN, POST /v1/scrape → JOB, poll GET /v1/jobs/$JOB; access tokens expire after 900 seconds; re-login command. Browser scrape example (render_js, screenshot, include_html, timeout_seconds 60). Artifacts: list, download (307 to presigned URL; `curl --resolve minio:9000:127.0.0.1`), and the direct-download fallback. API keys: POST /v1/keys with scopes; plaintext `sf_live_...` shown once.

   **7.7 Configuration** (all from scrapeflow/.env; recreate containers after changes): sub-tables for Required secrets (API_KEY_PEPPER, JWT_SECRET, WEBHOOK_SECRET_KEY, AUTOMATION_SECRET_KEY, POSTGRES_PASSWORD, DATABASE_URL, REDIS_URL) with secret-generation one-liner; Browser & egress (SELENIUM_REMOTE_URL, EGRESS_PROXY_URL, EGRESS_ALLOWED_PORTS, JOB_TIMEOUT_SECONDS, HTTP_TIMEOUT_SECONDS, HTTP_MAX_BYTES); Artifact storage (ARTIFACTS_ENDPOINT, ARTIFACTS_BUCKET, ARTIFACTS_ACCESS_KEY/SECRET_KEY, ARTIFACTS_RETENTION_DAYS); Proxies and country codes (off by default; static list `COUNTRY|proxy-url` and rotating gateway with `{country}`; ISO 3166-1 alpha-2 uppercase, use GB not UK; per-job `proxy_country`; unconfigured country returns 422); Plans, quotas, billing (BILLING_ENABLED=false by default, Stripe variables, 402/429 typed responses); Metrics (METRICS_ENABLED, METRICS_TOKEN bearer); Strix optional pentest (not required, never in PR gate, needs LLM key, install with `uv tool install strix-agent==1.7.0`, STRIX_LLM / LLM_API_KEY, per-platform commands for source audit and live scan, reports in scrapeflow/strix_runs/, GitHub Actions secrets, marked UNVERIFIED because no real scan has run).

   **7.8 Local development without Docker**: start Postgres and Redis containers, .env values pointing to 127.0.0.1, `uv sync --dev`, `uv run alembic upgrade head`, optional seed, uvicorn command, worker, beat, standalone egress proxy commands, and dashboard (`cd apps/web && npm ci && npm run dev`, `.env.local` with API_BASE_URL and NEXT_PUBLIC_APP_NAME). Note: POSIX shell; on Windows use WSL 2 or Git Bash.

   **7.9 Tests & quality gates**: Python (`uv run ruff check apps packages tests`, `ruff format --check`, `mypy apps packages`, `pytest -q`) with the disposable Postgres/Redis integration test setup (bash and PowerShell). Web (`npm run lint`, `typecheck`, `test`, `build`, optional `npx playwright install chromium` then `npm run e2e`). Note the 3 known local skips.

   **7.10 Production deployment** (mark "Not verified live"): server prerequisites (Linux host, Docker + Compose v2, DNS A/AAAA record, ports 80/443); production .env template (APP_ENV=production, PUBLIC_BASE_URL, CORS_ORIGINS, DOMAIN, ACME_EMAIL, POSTGRES_*, DATABASE_URL, REDIS_URL, secrets, MinIO vars, BILLING_ENABLED=false, METRICS_*); build and start commands with `deploy/compose.prod.yml`; verify commands over HTTPS with METRICS_TOKEN; operations links (docs/runbook.md, docs/security-checklist.md, docs/FINAL_REPORT.md); optional observability overlay with Prometheus and Grafana bound to loopback.

   **7.11 Troubleshooting accordion** with ALL 17 rows from the guide (symptom / likely cause / fix): migrate failed; password authentication failed → fix-db-password; MinIO 401 → SF_S3_MODE=s3mock; port already allocated; PowerShell script disabled; SF_S3_MODE not recognized in PowerShell; curl alias in PowerShell → curl.exe; docker not recognized on Windows; macOS python3 missing; macOS Docker daemon not running; Browser jobs require EGRESS_PROXY_URL; UPSTREAM_ERROR after timeout (wait_for / example.com has no h1); 401 after a while (900 s token); 402/429; dashboard 502; DevToolsActivePort file doesn't exist (shm_size 2g); Future attached to a different loop. Include a searchable filter input above the accordion and a "Useful diagnostics" code block.

   **7.12 Routine controls**: start/update, stop, reset (destructive warning), force-recreate, seed, alembic current/heads; Windows replacement note; named volumes scrapeflow_pgdata, scrapeflow_redisdata, scrapeflow_miniodata.

   **7.13 Security checklist before publishing** as an interactive checklist (checkboxes, state in memory only): .env not tracked; .env.legacy, .venv, node_modules, .next, .run, coverage, screenshots, DB dumps not tracked; random dev secrets; no secrets in commits; production secrets via environment/secret manager; APP_ENV=production; /metrics private or token-protected; BILLING_ENABLED=false until real keys; rotate leaked secrets (rotate first, then rewrite history).

   **7.14 Publish to GitHub**: commands (`git branch -M main`, add remote SSH/HTTPS, `git push -u origin main`), CI jobs table (backend, integration, web, image), notes (hosted CI not yet run; add branch protection).

   **7.15 Project layout**: tree of scrapeflow/ (apps/api, apps/worker, apps/web, packages/core, migrations, tests, deploy, scripts) and docs/ (runbook.md, security-checklist.md, FINAL_REPORT.md, analysis/), plus useful entry points list.

   All Setup copy lives in typed data files (src/data/setup/*.ts). Every code block has a copy button with an aria-live "Copied!" toast, a language label, and light syntax highlighting (use a small highlighter like prism-react-renderer). Include "Also available on GitHub: SETUP.md" link at the end.

8. **Security highlights** (6 cards): SSRF-safe validating proxy with IP pinning; JWT access tokens + rotating hashed refresh tokens; peppered, hashed API keys shown once; encrypted webhook secrets; atomic Redis token-bucket rate limits and plan quotas; same-origin BFF with httpOnly refresh cookie and in-memory access token. Add an advisory note on Strix AI pentesting (not in PR gate, unverified until a real scan runs).

9. **Presentation PDF Preview** (important):
   - File: `ScrapeFlow-Project-Presentation.pdf` (37 pages, 16:9) at `/public/ScrapeFlow-Project-Presentation.pdf`.
   - `PdfViewer` with react-pdf: responsive 16:9 canvas, Previous/Next, page input "3 / 37", keyboard arrows, zoom in/out, fullscreen, lazy thumbnail strip, loading skeleton, error state that falls back to `<iframe src="/ScrapeFlow-Project-Presentation.pdf">` plus a prominent "Download PDF" button and "Open in new tab" link.
   - pdf.js worker for Vite: `new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url)`.
   - Lazy-load this section (React.lazy + Suspense).

10. **Verified vs Unverified**: two-column card. Verified: dev Compose stack (11 services), real browser scrape via Selenium Grid with screenshot/HTML/JSON artifacts, presigned artifact download, JWT auth and dashboard session, Celery Beat/reaper/retention/worker metrics, 322 Python tests (83.08% coverage) + ruff + mypy, 30 Vitest tests + lint + typecheck + build, Playwright E2E 5 passed / 2 skipped. Not verified: live Stripe checkout/portal, official MinIO image and lifecycle, production Caddy topology, commercial proxy gateway, real external webhook receiver, hosted GitHub Actions run, Locust capacity numbers, native Windows PowerShell 5.1 / native macOS runs, Strix pentest run.

11. **Screenshots gallery**: responsive grid of 6 placeholder cards (Jobs list, New scrape builder, Automation builder, Schedules, API keys, Billing) driven by a data array pointing to /public/screenshots/*.png, with gradient placeholders as fallback if the image is missing, and a click-to-open lightbox.

12. **FAQ** accordion (5 items: What is ScrapeFlow? Do I need Docker? Is Stripe required? Why is the API not launching Chrome? What is unverified?) and **Footer** (repo link, back-to-top button, note "Documentation site for ScrapeFlow").

## QUALITY REQUIREMENTS
- SEO: title, meta description, Open Graph + Twitter tags, SVG favicon (gradient "SF"), lang="en".
- Performance: lazy-load heavy components (PdfViewer, syntax highlighter), no layout shift, target Lighthouse 90+.
- All content in typed data files under src/data so copy can be edited without touching components.
- Do not invent metrics beyond those given. Never claim unverified items work.
- Add a project README.md explaining how to replace the PDF, add screenshots and update setup content.
- Verify `npm run build` passes before finishing.