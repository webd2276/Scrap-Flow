import type { SetupSubsection } from "./types";

export const CONFIGURATION_SECTIONS: SetupSubsection[] = [
  {
    id: "configuration",
    number: "7.7",
    title: "Configuration",
    blocks: [
      {
        type: "paragraph",
        text: "Everything is read from `scrapeflow/.env`. Restart or recreate the affected containers after changing values:",
      },
      {
        type: "code",
        language: "bash",
        label: "Restart after an env change",
        code: "./scripts/run.sh\n# or, for a targeted restart:\ndocker compose --project-directory . --env-file .env up -d --force-recreate api worker beat",
      },
      { type: "subheading", text: "7.7.1 Required secrets" },
      {
        type: "table",
        head: ["Variable", "Purpose"],
        rows: [
          ["`API_KEY_PEPPER`", "Peppers API-key hashes; 32+ random characters"],
          ["`JWT_SECRET`", "Signs access tokens; 32+ random characters"],
          ["`WEBHOOK_SECRET_KEY`", "Encrypts per-org webhook signing secrets"],
          ["`AUTOMATION_SECRET_KEY`", "Seals transient automation secrets (empty = derive from JWT)"],
          ["`POSTGRES_PASSWORD`", "Must match the password in `DATABASE_URL`"],
          ["`DATABASE_URL`", "`postgresql+asyncpg://user:pass@host:5432/db`"],
          ["`REDIS_URL`", "`redis://host:6379/0`"],
        ],
      },
      {
        type: "paragraph",
        text: "Generate a value with:",
      },
      {
        type: "code",
        language: "bash",
        label: "Secret generator",
        code: "python3 -c \"import secrets; print(secrets.token_urlsafe(48))\"",
      },
      {
        type: "paragraph",
        text: "`scripts/generate_env.py` fills all of these for local use.",
      },
      { type: "subheading", text: "Browser and egress" },
      {
        type: "table",
        head: ["Variable", "Meaning"],
        rows: [
          ["`SELENIUM_REMOTE_URL`", "Grid endpoint (`http://selenium:4444/wd/hub` in Compose)"],
          ["`EGRESS_PROXY_URL`", "Validating proxy every scrape uses (`http://egress-proxy:8888`)"],
          ["`EGRESS_ALLOWED_PORTS`", "Allowed destination ports, default `80,443`"],
          ["`JOB_TIMEOUT_SECONDS`", "Hard job deadline"],
          ["`HTTP_TIMEOUT_SECONDS`", "Per-request HTTP timeout"],
          ["`HTTP_MAX_BYTES`", "Response size cap"],
        ],
      },
      {
        type: "paragraph",
        text: "The API never launches Chrome. Browser execution is worker-only; the API fails closed when a browser job cannot be routed through validated egress.",
      },
      { type: "subheading", text: "Artifact storage" },
      {
        type: "table",
        head: ["Variable", "Meaning"],
        rows: [
          ["`ARTIFACTS_ENDPOINT`", "S3 endpoint (`http://minio:9000` in Compose)"],
          ["`ARTIFACTS_BUCKET`", "Bucket name"],
          ["`ARTIFACTS_ACCESS_KEY` / `ARTIFACTS_SECRET_KEY`", "S3 credentials"],
          ["`ARTIFACTS_RETENTION_DAYS`", "Retention for cleanup"],
        ],
      },
      {
        type: "paragraph",
        text: "Leave `ARTIFACTS_ENDPOINT` empty to use the local filesystem (development and tests only).",
      },
      { type: "subheading", text: "Proxies and country codes" },
      {
        type: "paragraph",
        text: "Proxy support is **off by default**. Enable exactly one provider.",
      },
      {
        type: "paragraph",
        text: "Static list — `COUNTRY|proxy-url`:",
      },
      {
        type: "code",
        language: "dotenv",
        label: "Static proxy list",
        code: "PROXY_ENABLED=true\nPROXY_STATIC_LIST=DE|http://user:pass@proxy-a.example:8080,US|http://user:pass@proxy-b.example:8080",
      },
      {
        type: "paragraph",
        text: "Rotating gateway — `{country}` is expanded per request:",
      },
      {
        type: "code",
        language: "dotenv",
        label: "Rotating gateway",
        code: "PROXY_ENABLED=true\nPROXY_GATEWAY_URL=http://user-{country}:pass@gateway.example.com:8080\nPROXY_GATEWAY_COUNTRIES=DE,US,GB\nPROXY_GATEWAY_DEFAULT_COUNTRY=US",
      },
      {
        type: "paragraph",
        text: "Country codes are ISO 3166-1 alpha-2, exactly two uppercase letters (`US`, `DE`, `GB`, `IN`, `AE`, `SG`). Use `GB`, not `UK`. Only advertise countries your provider actually serves.",
      },
      {
        type: "paragraph",
        text: "Request a country per job:",
      },
      {
        type: "code",
        language: "json",
        label: "Per-job country",
        code: "{\n  \"url\": \"https://example.com/\",\n  \"render_js\": true,\n  \"proxy_country\": \"DE\"\n}",
      },
      {
        type: "paragraph",
        text: "A country that is not configured returns `422`. With proxies disabled, sending `proxy_country` also returns `422`. Omitting it uses the default/any endpoint. Proxy jobs cost extra credits.",
      },
      { type: "subheading", text: "Plans, quotas, and billing" },
      {
        type: "list",
        items: [
          "Free/starter/pro/business plans and credit costs live in `packages/core/plans.py`.",
          "Quota and rate-limit failures use typed `402`/`429` responses with headers.",
          "Billing stays disabled until Stripe keys and price IDs are set.",
        ],
      },
      {
        type: "code",
        language: "dotenv",
        label: "Billing",
        code: "BILLING_ENABLED=false\nSTRIPE_SECRET_KEY=\nSTRIPE_WEBHOOK_SECRET=\nSTRIPE_PRICE_STARTER=\nSTRIPE_PRICE_PRO=\nSTRIPE_PRICE_BUSINESS=",
      },
      { type: "subheading", text: "Metrics" },
      {
        type: "paragraph",
        text: "`METRICS_ENABLED=true` exposes `/metrics`. If the endpoint is reachable outside a private network, set a random `METRICS_TOKEN`; requests must then send `Authorization: Bearer <token>`.",
      },
      { type: "subheading", text: "Strix automated pentesting (optional)" },
      {
        type: "callout",
        tone: "info",
        title: "Optional, advisory — and unverified",
        text: "Strix is an autonomous AI pentester. It is not required to run ScrapeFlow, is never part of the pull-request gate, needs an LLM key, costs money, and produces findings a human must triage. No real scan has run yet.",
      },
      {
        type: "code",
        language: "bash",
        label: "Install once",
        code: "uv tool install strix-agent==1.7.0\nexport STRIX_LLM=\"openrouter/z-ai/glm-5.3\"\nexport LLM_API_KEY=\"...\"\ncd scrapeflow",
      },
      {
        type: "table",
        head: ["Platform", "Source audit", "Live API on :8000"],
        rows: [
          ["Linux", "`./scripts/security-scan.sh`", "`./scripts/security-scan.sh live`"],
          ["macOS", "`./scripts/security-scan-macos.sh`", "`./scripts/security-scan-macos.sh live`"],
          ["Windows PowerShell", "`.\\scripts\\security-scan.ps1`", "`.\\scripts\\security-scan.ps1 live`"],
          ["Windows CMD", "`scripts\\security-scan.cmd`", "`scripts\\security-scan.cmd live`"],
        ],
      },
      {
        type: "paragraph",
        text: "On Windows set `$env:STRIX_LLM` and `$env:LLM_API_KEY` before running. Source scans execute in a detached worktree at `HEAD`, so the agent cannot edit your working tree; live scans download `/openapi.json` and stay on localhost. Reports land in `scrapeflow/strix_runs/` and `strix view` opens the dashboard.",
      },
      {
        type: "paragraph",
        text: "For GitHub Actions, add repository secrets `STRIX_LLM` and `LLM_API_KEY`, then run the **Strix pentest** workflow manually from the Actions tab. Without the secrets the job skips with a warning instead of failing. Budget caps, exit codes and the safety rules are in `docs/security/strix.md`.",
      },
    ],
  },
  {
    id: "local-development",
    number: "7.8",
    title: "Local development without Docker",
    blocks: [
      {
        type: "paragraph",
        text: "The commands in this section assume a POSIX shell. On Windows, use WSL 2 or Git Bash, or translate the environment prefixes to PowerShell (`$env:DATABASE_URL = '...'`). The Docker path above works natively in PowerShell.",
      },
      {
        type: "paragraph",
        text: "You still need PostgreSQL and Redis. The quickest way is two containers:",
      },
      {
        type: "code",
        language: "bash",
        label: "Dependencies only",
        code: "docker run -d --name sf-postgres \\\n  -e POSTGRES_USER=scrapeflow \\\n  -e POSTGRES_PASSWORD=scrapeflow \\\n  -e POSTGRES_DB=scrapeflow \\\n  -p 5432:5432 postgres:16-alpine\n\ndocker run -d --name sf-redis -p 6379:6379 redis:7-alpine",
      },
      {
        type: "paragraph",
        text: "Point `scrapeflow/.env` at the host ports and remove Compose-only hostnames:",
      },
      {
        type: "code",
        language: "dotenv",
        label: "Host-process .env",
        code: "DATABASE_URL=postgresql+asyncpg://scrapeflow:scrapeflow@127.0.0.1:5432/scrapeflow\nREDIS_URL=redis://127.0.0.1:6379/0\n\n# Host processes cannot resolve \"egress-proxy\" or \"selenium\".\n# For HTTP jobs, either run the standalone proxy and use loopback:\nEGRESS_PROXY_URL=http://127.0.0.1:8888\n# ...or leave it empty so the worker starts an in-process validating proxy:\n# EGRESS_PROXY_URL=\nSELENIUM_REMOTE_URL=",
      },
      {
        type: "paragraph",
        text: "Install, migrate, and start the API:",
      },
      {
        type: "code",
        language: "bash",
        label: "API",
        code: "uv sync --dev\nuv run alembic upgrade head\nuv run python -m scripts.seed        # optional demo data\nuv run uvicorn apps.api.asgi:app --reload --port 8000",
      },
      {
        type: "paragraph",
        text: "In separate terminals:",
      },
      {
        type: "code",
        language: "bash",
        label: "Worker, beat, egress proxy",
        code: "# Worker\nuv run celery -A apps.worker.celery_app worker \\\n  --loglevel=INFO --concurrency=1 --pool=solo --queues=jobs,celery\n\n# Beat (reaper, schedules, webhooks, retention, quota reconcile)\nuv run celery -A apps.worker.celery_app beat \\\n  --loglevel=INFO --schedule=/tmp/celerybeat-schedule\n\n# Standalone validating egress proxy (needed for browser jobs with remote Grid)\nEGRESS_PROXY_LISTEN_HOST=127.0.0.1 EGRESS_PROXY_LISTEN_PORT=8888 \\\n  uv run python -m apps.worker.egress_proxy",
      },
      {
        type: "paragraph",
        text: "Without `EGRESS_PROXY_URL`, the worker starts an in-process validating proxy for HTTP jobs. `render_js=false` works without Selenium; `render_js=true` needs a Grid and `SELENIUM_REMOTE_URL`.",
      },
      {
        type: "paragraph",
        text: "Dashboard:",
      },
      {
        type: "code",
        language: "bash",
        label: "Dashboard",
        code: "cd apps/web\nnpm ci\nnpm run dev        # http://127.0.0.1:3000",
      },
      {
        type: "paragraph",
        text: "`apps/web/.env.local` should contain:",
      },
      {
        type: "code",
        language: "dotenv",
        label: ".env.local",
        code: "API_BASE_URL=http://127.0.0.1:8000\nNEXT_PUBLIC_APP_NAME=ScrapeFlow",
      },
    ],
  },
  {
    id: "tests",
    number: "7.9",
    title: "Tests & quality gates",
    blocks: [
      { type: "subheading", text: "Python" },
      {
        type: "code",
        language: "bash",
        label: "Lint, typecheck, test",
        code: "cd scrapeflow\n\nuv run ruff check apps packages tests\nuv run ruff format --check apps packages tests\nuv run mypy apps packages\nuv run pytest -q",
      },
      {
        type: "paragraph",
        text: "Integration tests skip when `TEST_DATABASE_URL` / `TEST_REDIS_URL` are unset. Run them against disposable services:",
      },
      {
        type: "code",
        language: "bash",
        label: "Disposable test services",
        code: "docker run -d --name sf-test-pg -p 55432:5432 \\\n  -e POSTGRES_USER=scrapeflow -e POSTGRES_PASSWORD=scrapeflow \\\n  -e POSTGRES_DB=scrapeflow_test postgres:16-alpine\n\ndocker run -d --name sf-test-redis -p 56379:6379 redis:7-alpine",
      },
      {
        type: "code",
        language: "bash",
        label: "Integration tests",
        code: "TEST_DATABASE_URL='postgresql+asyncpg://scrapeflow:scrapeflow@127.0.0.1:55432/scrapeflow_test' \\\nTEST_REDIS_URL='redis://127.0.0.1:56379/0' \\\nuv run pytest -q",
      },
      {
        type: "code",
        language: "powershell",
        label: "Windows PowerShell equivalent",
        code: "$env:TEST_DATABASE_URL = 'postgresql+asyncpg://scrapeflow:scrapeflow@127.0.0.1:55432/scrapeflow_test'\n$env:TEST_REDIS_URL = 'redis://127.0.0.1:56379/0'\nuv run pytest -q\nRemove-Item Env:TEST_DATABASE_URL, Env:TEST_REDIS_URL",
      },
      { type: "subheading", text: "Web" },
      {
        type: "code",
        language: "bash",
        label: "Dashboard gates",
        code: "cd scrapeflow/apps/web\nnpm run lint\nnpm run typecheck\nnpm test\nnpm run build",
      },
      {
        type: "paragraph",
        text: "Optional browser journey (needs the API, PostgreSQL, and Redis running):",
      },
      {
        type: "code",
        language: "bash",
        label: "E2E",
        code: "npx playwright install chromium\nnpm run e2e",
      },
      {
        type: "paragraph",
        text: "Known local skips: one test needs `CHROME_BINARY` for a local Chrome run, one worker test needs a Grid, and one load-script check needs `locust`.",
      },
    ],
  },
];
