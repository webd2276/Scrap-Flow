# ScrapeFlow

Multi-tenant web scraping and browser-automation API. This repository is being
rebuilt from the original single-process MVP into the production architecture
described in `docs/analysis/04-plan.md`.

**Status: Phase 1 (foundation) complete.** The scrape/automation/auth/billing
routes from the legacy MVP are intentionally not mounted yet; they are rebuilt
phase by phase. See `docs/analysis/02-gap-matrix.md` for the live gap list.

## Requirements

- Docker + Docker Compose (full stack), or
- Python 3.12 + `uv` and local PostgreSQL/Redis for development.

## Quick start (Docker)

```bash
cp .env.example .env
python3 scripts/generate_env.py     # only if .env does not exist; generates secrets
docker compose up --build
```

Then:

```bash
curl -s localhost:8000/health
curl -s localhost:8000/ready
```

API docs: <http://localhost:8000/docs> (disabled in production).

## Local development

```bash
uv sync --dev
uv run uvicorn apps.api.asgi:app --reload --port 8000
```

The API fails fast if `DATABASE_URL`, `REDIS_URL`, `API_KEY_PEPPER`,
`JWT_SECRET`, or `WEBHOOK_SECRET_KEY` are missing or shorter than 32 characters.

## Quality gates

```bash
make lint     # ruff check + format check
make type     # mypy strict
make test     # pytest
make cov      # pytest with coverage
```

## Layout

```
apps/api        FastAPI app (middleware, routers, services)
apps/worker     Celery workers and Selenium runner
apps/web        Next.js dashboard (later phase)
packages/core   settings, errors, logging, db, security primitives
migrations      Alembic
tests           unit / integration / e2e
deploy          production compose, Caddy, dashboards
```

## Current endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | none | liveness |
| GET | `/ready` | none | Postgres + Redis readiness |
| GET | `/metrics` | none | Prometheus (planned Phase 9) |

Everything else is listed in the plan and will appear phase by phase.
