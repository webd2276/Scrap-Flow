import type { SetupSubsection } from "./types";

export const OPERATION_SECTIONS: SetupSubsection[] = [
  {
    id: "production",
    number: "7.10",
    title: "Production deployment",
    blocks: [
      {
        type: "callout",
        tone: "warn",
        title: "Not verified live",
        text: "The production Caddy topology needs a real domain and was not started during the project's local verification. The steps below are the intended path, not a proven run.",
      },
      {
        type: "paragraph",
        text: "This section uses `deploy/compose.prod.yml`, which runs everything behind Caddy with automatic TLS. Run these commands on the Linux server (over SSH from Windows or macOS); the production topology is not a desktop deployment.",
      },
      { type: "subheading", text: "10.1 Server prerequisites" },
      {
        type: "list",
        items: [
          "A Linux host with Docker + Compose v2.",
          "A DNS `A`/`AAAA` record for your domain pointing at the host.",
          "Ports `80` and `443` open.",
          "A production `.env`; never reuse development secrets.",
        ],
      },
      { type: "subheading", text: "10.2 Production .env" },
      {
        type: "paragraph",
        text: "Start from `.env.example`, then set at least:",
      },
      {
        type: "code",
        language: "dotenv",
        label: "deploy/compose.prod.yml environment",
        code: "APP_ENV=production\nPUBLIC_BASE_URL=https://scrapeflow.example.com\nCORS_ORIGINS=https://scrapeflow.example.com\n\nDOMAIN=scrapeflow.example.com\nACME_EMAIL=ops@example.com\n\nPOSTGRES_USER=scrapeflow\nPOSTGRES_PASSWORD=<32+ random characters>\nPOSTGRES_DB=scrapeflow\nDATABASE_URL=postgresql+asyncpg://scrapeflow:<same password>@postgres:5432/scrapeflow\nREDIS_URL=redis://redis:6379/0\n\nAPI_KEY_PEPPER=<32+ random characters>\nJWT_SECRET=<32+ random characters>\nWEBHOOK_SECRET_KEY=<32+ random characters>\nAUTOMATION_SECRET_KEY=<32+ random characters>\n\nARTIFACTS_BUCKET=scrapeflow\nMINIO_ROOT_USER=scrapeflow\nMINIO_ROOT_PASSWORD=<32+ random characters>\nARTIFACTS_ACCESS_KEY=<same as MINIO_ROOT_USER>\nARTIFACTS_SECRET_KEY=<same as MINIO_ROOT_PASSWORD>\n\nBILLING_ENABLED=false\nMETRICS_ENABLED=true\nMETRICS_TOKEN=<32+ random characters>",
      },
      {
        type: "paragraph",
        text: "If the pinned MinIO image is unavailable in your registry, mirror a working image and set `MINIO_IMAGE` in `.env`.",
      },
      { type: "subheading", text: "10.3 Build and start" },
      {
        type: "code",
        language: "bash",
        label: "Build images and start",
        code: "cd scrapeflow\n\ndocker compose --project-directory . -f deploy/compose.prod.yml \\\n  --env-file .env config >/dev/null\n\ndocker build -t scrapeflow:$(git rev-parse --short HEAD) .\ndocker build -t scrapeflow-web:$(git rev-parse --short HEAD) apps/web\n\nSCRAPEFLOW_IMAGE=scrapeflow:$(git rev-parse --short HEAD) \\\n  docker compose --project-directory . -f deploy/compose.prod.yml \\\n  --env-file .env up -d",
      },
      {
        type: "paragraph",
        text: "Only Caddy publishes ports. The API, dashboard, workers, Grid, Postgres, Redis, and MinIO stay on the internal network.",
      },
      { type: "subheading", text: "10.4 Verify" },
      {
        type: "code",
        language: "bash",
        label: "HTTPS checks",
        code: "curl -fsS https://$DOMAIN/health\ncurl -fsS https://$DOMAIN/ready\ncurl -fsS -H \"Authorization: Bearer $METRICS_TOKEN\" https://$DOMAIN/metrics | head",
      },
      {
        type: "paragraph",
        text: "Then complete the signup → scrape → artifact flow from section 6 over HTTPS.",
      },
      { type: "subheading", text: "10.5 Operations" },
      {
        type: "list",
        items: [
          "Follow logs: `docker compose -f deploy/compose.prod.yml logs -f api worker beat caddy`",
          "Backup/restore, rollback, scaling, and incident procedures: `docs/runbook.md`",
          "Security checklist: `docs/security-checklist.md`",
          "Release evidence and remaining external gaps: `docs/FINAL_REPORT.md`",
        ],
      },
    ],
  },
  {
    id: "troubleshooting",
    number: "7.11",
    title: "Troubleshooting",
    blocks: [
      {
        type: "paragraph",
        text: "Filter by symptom. Each row names the likely cause and the fix.",
      },
      {
        type: "accordion",
        filterable: true,
        items: [
          {
            question: "`service \"migrate\" didn't complete successfully`",
            answer: "**Cause:** the migration failed. **Fix:** read `docker compose logs migrate`, correct the failing revision or environment value, then start again.",
          },
          {
            question: "`password authentication failed for user \"scrapeflow\"`",
            answer: "**Cause:** the Postgres volume was initialized with an older password than the current `.env`. **Fix:** `./scripts/run.sh fix-db-password` (keeps data) or `reset` (deletes data). On Windows use `.\\scripts\\run.ps1`.",
          },
          {
            question: "MinIO image pull fails with `401 UNAUTHORIZED`",
            answer: "**Cause:** the pinned tag is not available from your registry. **Fix:** `SF_S3_MODE=s3mock ./scripts/run.sh`, `$env:SF_S3_MODE='s3mock'; .\\scripts\\run.ps1`, or mirror an image and set `MINIO_IMAGE`.",
          },
          {
            question: "`port is already allocated` on 8000/3000",
            answer: "**Cause:** another stack or service is using the port. **Fix:** stop the stack (`./scripts/run.sh stop` or `.\\scripts\\run.ps1 stop`), then retry. Linux: `ss -ltnp | grep -E ':8000|:3000'`; Windows: `netstat -ano | findstr :8000`.",
          },
          {
            question: "PowerShell: `running scripts is disabled on this system`",
            answer: "**Cause:** the execution policy blocks `.ps1` files. **Fix:** run `scripts\\run.cmd` or `powershell -ExecutionPolicy Bypass -File .\\scripts\\run.ps1`.",
          },
          {
            question: "PowerShell: `SF_S3_MODE is not recognized`",
            answer: "**Cause:** a Bash-style environment assignment was used in PowerShell. **Fix:** use `$env:SF_S3_MODE = 's3mock'` before the command.",
          },
          {
            question: "PowerShell: `curl` output looks like HTML or `-fsS` is rejected",
            answer: "**Cause:** `curl` is an alias for `Invoke-WebRequest`. **Fix:** use `curl.exe` in commands.",
          },
          {
            question: "Windows: `docker` is not recognized",
            answer: "**Cause:** Docker Desktop is not running, or PATH was updated after the terminal opened. **Fix:** start Docker Desktop and open a new PowerShell window.",
          },
          {
            question: "macOS: `python3: command not found`",
            answer: "**Cause:** Python 3 is not installed; the runner only needs it to create `.env` or repair the DB password. **Fix:** `xcode-select --install` or `brew install python`.",
          },
          {
            question: "macOS: `Cannot connect to the Docker daemon`",
            answer: "**Cause:** Docker Desktop is not running. **Fix:** start Docker Desktop and wait for the whale icon to be idle.",
          },
          {
            question: "Browser job fails with `Browser jobs require EGRESS_PROXY_URL`",
            answer: "**Cause:** the worker did not receive the shared backend environment. **Fix:** use the committed Compose files or set `EGRESS_PROXY_URL` on the worker.",
          },
          {
            question: "Job ends `UPSTREAM_ERROR` after a timeout",
            answer: "**Cause:** the page never matched `wait_for`. **Fix:** remove or relax `wait_for`; `example.com` has no `<h1>`.",
          },
          {
            question: "`401 Unauthorized` after a while",
            answer: "**Cause:** the access token expired (900 s). **Fix:** log in again or use an API key.",
          },
          {
            question: "`402` / `429` responses",
            answer: "**Cause:** plan quota or rate limit. **Fix:** inspect `Retry-After` / quota headers, or raise the plan.",
          },
          {
            question: "Dashboard returns `502`",
            answer: "**Cause:** the API is not healthy. **Fix:** run the `status` command for your platform and check the API logs.",
          },
          {
            question: "`DevToolsActivePort file doesn't exist`",
            answer: "**Cause:** Chrome was not started headless, or the Grid lacks shared memory. **Fix:** keep `--headless=new`, `--disable-gpu`; the Grid needs `shm_size: 2g`.",
          },
          {
            question: "`Future attached to a different loop` in worker logs",
            answer: "**Cause:** an old worker image reused a pooled connection across Celery task loops. **Fix:** rebuild with the current code (run the start command again).",
          },
        ],
      },
      { type: "subheading", text: "Useful diagnostics" },
      {
        type: "code",
        language: "bash",
        label: "Linux / macOS",
        code: "./scripts/run.sh status\n./scripts/run.sh logs\ndocker compose --project-directory . --env-file .env logs --tail=100 migrate\ndocker inspect scrapeflow-worker-1 --format '{{range .Config.Env}}{{println .}}{{end}}' | sort",
      },
      {
        type: "code",
        language: "powershell",
        label: "Windows PowerShell",
        code: ".\\scripts\\run.ps1 status\n.\\scripts\\run.ps1 logs\ndocker compose --project-directory . --env-file .env logs --tail=100 migrate\ndocker inspect scrapeflow-worker-1 --format '{{range .Config.Env}}{{println .}}{{end}}'",
      },
    ],
  },
  {
    id: "routine-controls",
    number: "7.12",
    title: "Routine controls",
    blocks: [
      {
        type: "code",
        language: "bash",
        label: "Day-to-day commands",
        code: "# Start or update\n./scripts/run.sh\n\n# Stop without losing data\n./scripts/run.sh stop\n\n# Delete containers and local data volumes (destructive)\n./scripts/run.sh reset\n\n# Recreate one service after an env change\ndocker compose --project-directory . --env-file .env up -d --force-recreate api worker beat\n\n# Seed demo account (first run prints the password; each run prints a new key)\n./scripts/run.sh seed\n\n# View database migrations\ndocker compose exec api alembic current\ndocker compose exec api alembic heads",
      },
      {
        type: "paragraph",
        text: "On Windows replace each `./scripts/run.sh` command with `.\\scripts\\run.ps1`; the direct `docker compose` commands are identical.",
      },
      {
        type: "paragraph",
        text: "Data lives in named Docker volumes: `scrapeflow_pgdata`, `scrapeflow_redisdata`, and `scrapeflow_miniodata` (or the S3-mock container). Back them up before `reset`.",
      },
    ],
  },
  {
    id: "security-checklist",
    number: "7.13",
    title: "Security checklist before publishing",
    blocks: [
      {
        type: "paragraph",
        text: "Tick each item before the repository or a deployment becomes public. The state is kept in memory only and is not stored.",
      },
      {
        type: "checklist",
        items: [
          "`.env` is not tracked.",
          "`scrapeflow/.env.legacy`, `.venv/`, `node_modules/`, `.next/`, `.run/`, coverage files, screenshots, and database dumps are not tracked.",
          "All development secrets in `.env` are random, not reused, and different from production.",
          "No API keys, JWT secrets, Stripe keys, proxy credentials, or webhook secrets appear in commits, issue text, or screenshots.",
          "Production secrets are injected through the server environment or a secret manager, never baked into images.",
          "`APP_ENV=production` in production (disables `/docs` and enforces secure cookies).",
          "`/metrics` is private or protected by `METRICS_TOKEN`.",
          "`BILLING_ENABLED=false` until real Stripe keys are configured.",
          "Rotate any secret that was ever committed by accident.",
        ],
      },
      {
        type: "code",
        language: "bash",
        label: "Confirm .env is ignored",
        code: "git check-ignore -v scrapeflow/.env\ngit status --short",
      },
      {
        type: "paragraph",
        text: "If a secret was committed, rotate it first, then rewrite history; deleting the file in a later commit is not enough.",
      },
    ],
  },
  {
    id: "publish",
    number: "7.14",
    title: "Publish to GitHub",
    blocks: [
      {
        type: "paragraph",
        text: "The local branch may be named `master`. GitHub's default is `main`; the CI workflow accepts both, but renaming avoids surprises.",
      },
      {
        type: "code",
        language: "bash",
        label: "Push the repository",
        code: "cd web-scrapping-tool\n\n# 1. Make sure the working tree is clean and secrets are ignored\ngit status --short\ngit check-ignore -v scrapeflow/.env\n\n# 2. Use main\ngit branch -M main\n\n# 3. Create an empty repository on GitHub (no README, no .gitignore),\n#    then connect it:\ngit remote add origin git@github.com:<YOUR_USER>/<YOUR_REPO>.git\n# HTTPS alternative:\n# git remote add origin https://github.com/<YOUR_USER>/<YOUR_REPO>.git\n\n# 4. Push\ngit push -u origin main",
      },
      {
        type: "paragraph",
        text: "If the remote already exists:",
      },
      {
        type: "code",
        language: "bash",
        label: "Update an existing remote",
        code: "git remote set-url origin git@github.com:<YOUR_USER>/<YOUR_REPO>.git\ngit push -u origin main",
      },
      {
        type: "paragraph",
        text: "After the push, open the **Actions** tab. `.github/workflows/ci.yml` runs:",
      },
      {
        type: "table",
        head: ["Job", "What it does"],
        rows: [
          ["`backend`", "Ruff, mypy, unit tests with coverage, `pip-audit`"],
          ["`integration`", "PostgreSQL + Redis services, integration tests"],
          ["`web`", "ESLint, typecheck, Vitest, production build"],
          ["`image`", "Builds the backend and dashboard Docker images"],
        ],
      },
      {
        type: "list",
        items: [
          "The workflow runs on pushes to `main` or `master` and on pull requests.",
          "No repository secrets are required for the default CI path.",
          "Hosted CI has not been executed from this local checkout; watch the first run and fix any runner-specific issues.",
          "Add a branch protection rule requiring CI before merge.",
        ],
      },
    ],
  },
  {
    id: "project-layout",
    number: "7.15",
    title: "Project layout",
    blocks: [
      {
        type: "code",
        language: "text",
        label: "Repository tree",
        code: "scrapeflow/\n  apps/api        FastAPI app, routers, services, middleware\n  apps/worker     Celery tasks, browser runner, egress proxy\n  apps/web        Next.js dashboard + same-origin BFF\n  packages/core   settings, DB, models, quotas, SSRF, security\n  migrations      Alembic migrations\n  tests           unit / integration / e2e / load\n  deploy          production Compose, Caddy, Prometheus, Grafana\n  scripts         run.sh, run-macos.sh, run.ps1, run.cmd, env generator, seed, bucket setup\ndocs/\n  runbook.md      deploy, rollback, backup, incident response\n  security-checklist.md\n  FINAL_REPORT.md verified scope and remaining external gaps\n  analysis/       gap matrix, system map, plan, risk review",
      },
      { type: "subheading", text: "Useful entry points" },
      {
        type: "list",
        items: [
          "API documentation (development): `http://127.0.0.1:8000/docs`",
          "OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`",
          "Health: `/health`; readiness: `/ready`; metrics: `/metrics`",
          "Scrape: `POST /v1/scrape`; jobs: `GET /v1/jobs/{id}`; artifacts: `GET /v1/jobs/{id}/artifacts`",
          "Automation: `POST /v1/automate`",
          "Schedules, exports, webhooks: see `scrapeflow/README.md`",
        ],
      },
      {
        type: "paragraph",
        text: "Also available on GitHub: [SETUP.md](https://github.com/webd2276/Scrap-Flow/blob/main/SETUP.md).",
      },
    ],
  },
];
