# ScrapeFlow operations runbook

Owner: platform on-call. This runbook covers the production topology in
`scrapeflow/deploy/compose.prod.yml` and the observability shipped in
Phase 9. Commands assume the working directory is `scrapeflow/` and that
`.env` holds production values.

## 1. Topology and dependencies

| Component | Responsibility | Stateful |
|---|---|---|
| `caddy` | TLS termination, `/v1/*` + health/metrics/docs to API, everything else to `web` | No |
| `api` | Auth, validation, quotas, idempotency, enqueue, exports | No |
| `worker` | Scrape/automation browser work, webhooks, schedule dispatch | No (Redis leases, PG source of truth) |
| `beat` | One scheduler; must never run more than one replica | No |
| `egress-proxy` | Resolves, validates, and pins every browser/HTTP destination | No |
| `selenium` | Grid browser nodes | Ephemeral |
| `web` | Next.js dashboard + same-origin BFF | No |
| `postgres` | Durable jobs, orgs, keys, ledger, schedules, outbox | **Yes** |
| `redis` | Celery broker, quotas, tokens, locks, session registry | Rebuildable, not authoritative |
| `minio` | Artifacts (screenshots, HTML) | **Yes** |

The API never launches Chrome. If `SELENIUM_REMOTE_URL` and the egress proxy
are not reachable, browser jobs fail with `503`; they do not fall back to a
local browser.

## 2. Deploy

Prerequisites: Docker with Compose v2, a DNS record for `DOMAIN`, and a
production `.env` generated from `.env.example` with every `CHANGE_ME`
replaced. `API_KEY_PEPPER`, `JWT_SECRET`, `WEBHOOK_SECRET_KEY`, and
`AUTOMATION_SECRET_KEY` must each be 32+ random characters and must never be
reused across environments.

```bash
cd scrapeflow
docker compose --project-directory . -f deploy/compose.prod.yml --env-file .env config >/dev/null
docker build -t scrapeflow:$(git rev-parse --short HEAD) .
docker build -t scrapeflow-web:$(git rev-parse --short HEAD) apps/web
SCRAPEFLOW_IMAGE=scrapeflow:$(git rev-parse --short HEAD) \
  docker compose --project-directory . -f deploy/compose.prod.yml --env-file .env up -d
```

The `migrate` one-shot service runs `alembic upgrade head` before the API and
worker start. Compose starts dependencies in health-check order.

Verify:

```bash
curl -fsS https://$DOMAIN/health
curl -fsS https://$DOMAIN/ready
curl -fsS -H "Authorization: Bearer $METRICS_TOKEN" https://$DOMAIN/metrics | head
```

`/ready` returning 503 means a probe failed; the response body names the
failed dependency. Do not route traffic to an instance that fails readiness.

Dashboard: browse to `https://$DOMAIN`, sign up, and confirm the job submission
page loads. The browser never receives the API origin or refresh token.

### Post-deploy full-stack smoke test

Run this once after every deploy. It exercises the API → queue → worker →
Grid → egress proxy path and the artifact store, not just liveness.

```bash
STAMP=$(date +%s)
EMAIL="smoke-${STAMP}@example.com"
TOKEN=$(curl -fsS -X POST "https://$DOMAIN/v1/auth/signup" \
  -H 'Content-Type: application/json' \
  -d "{\"org_name\":\"Smoke ${STAMP}\",\"email\":\"${EMAIL}\",\
\"password\":\"$(openssl rand -base64 24)\",\"tos_accepted\":true}" | jq -r .access_token)

JOB=$(curl -fsS -X POST "https://$DOMAIN/v1/scrape" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com/","render_js":true,
       "selectors":{"title":{"css":"title"}},"screenshot":true,
       "include_html":true,"timeout_seconds":60}' | jq -r .job.id)

for _ in $(seq 1 45); do
  STATUS=$(curl -fsS "https://$DOMAIN/v1/jobs/$JOB" \
    -H "Authorization: Bearer $TOKEN" | jq -r .status)
  case "$STATUS" in succeeded|failed|cancelled|timed_out) break;; esac
  sleep 2
done
test "$STATUS" = succeeded || { echo "smoke job ended as $STATUS"; exit 1; }

curl -fsS "https://$DOMAIN/v1/jobs/$JOB/artifacts" \
  -H "Authorization: Bearer $TOKEN" | jq -r '.[] | "\(.kind) \(.size_bytes) \(.sha256)"'
```

Expected: `STATUS=succeeded` and three artifacts (`result`, `html`,
`screenshot`) with non-zero sizes. The worker only exposes `9101` inside the
compose network, so read the counter through the container:

```bash
docker compose --project-directory . -f deploy/compose.prod.yml --env-file .env \
  exec worker python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:9101/metrics').read().decode())" \
  | grep scrapeflow_jobs_total
```

A job that stays `queued` means Beat/worker are not consuming; `running` past
its timeout points at Grid or the egress proxy. Check `docker compose logs
worker beat selenium egress-proxy` before rolling back.

### Configuration that must not be skipped

- `METRICS_ENABLED=true` and a random `METRICS_TOKEN` when `/metrics` is
  reachable through Caddy. Without a token the endpoint is public.
- `SENTRY_DSN` so API exceptions include stack traces and release tags.
- `APP_ENV=production` so `/docs` is disabled and secure cookies are enforced.
- Leave `BILLING_ENABLED=false` until real Stripe keys and price IDs are set.
- Set `PROXY_ENABLED=false` unless exactly one provider is configured.

## 3. Rollback

Application rollback uses the previous immutable image tag. Migrations are
forward-only; do not downgrade a production database unless the release notes
explicitly include a tested downgrade.

```bash
PREVIOUS=scrapeflow:<previous-sha>
SCRAPEFLOW_IMAGE=$PREVIOUS \
  docker compose --project-directory . -f deploy/compose.prod.yml --env-file .env up -d api worker beat
```

The dashboard has its own image; rebuild or redeploy the previous
`scrapeflow-web:<sha>` through your registry. Observability changes are
additive: removing Prometheus/Grafana does not affect the API.

## 4. Backup and restore

### PostgreSQL (authoritative)

```bash
mkdir -p backups
docker compose --project-directory . -f deploy/compose.prod.yml --env-file .env \
  exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' \
  > backups/scrapeflow-$(date +%F-%H%M).dump
```

Restore into a maintained database:

```bash
docker compose --project-directory . -f deploy/compose.prod.yml --env-file .env \
  exec -T postgres sh -c 'pg_restore --clean --if-exists -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < backups/scrapeflow-YYYY-MM-DD-HHMM.dump
```

Restores are destructive; stop `api`, `worker`, and `beat` first, restore, run
`alembic upgrade head`, verify `/ready`, then restart. Test the restore drill
quarterly on a disposable database.

### MinIO artifacts

Artifacts have a plan-based retention window and expire on their own. Back up
the bucket only when contractually required:

```bash
docker run --rm --network scrapeflow-prod_app_net \
  -e MC_HOST_src=http://$MINIO_ROOT_USER:$MINIO_ROOT_PASSWORD@minio:9000 \
  -v "$PWD/backups:/backup" minio/mc mirror src/$ARTIFACTS_BUCKET /backup/artifacts
```

### Redis

Redis is not authoritative. Losing it loses queued Celery messages (the reaper
requeues jobs whose leases expire), token buckets, and session registry keys.
Jobs still in `queued`/`running` are reconciled by the worker reaper. Do not
restore Redis over a live instance; rebuild empty and let the reaper recover.

## 5. Scaling

- **API**: add replicas behind Caddy. uvicorn trusts forwarded headers; keep
  `--proxy-headers` and the private network only.
- **Workers**: scale replicas or `--concurrency` (compose default 8 in prod).
  One browser session per job; capacity is bounded by Grid nodes and worker
  memory. Keep `--max-tasks-per-child` to contain browser leaks.
- **Beat**: exactly one replica. Multiple beats create duplicate schedule
  attempts; `schedule_runs.run_key` still deduplicates, but alert on skipped
  dispatches.
- **PostgreSQL**: scale vertically first. Connection pools are per process
  (`DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW`); budget for API replicas +
  worker prefork children + beat.
- **Redis**: size for the broker backlog and quota Lua scripts; monitor
  `scrapeflow_queue_depth`.
- **Worker metrics**: each worker container exposes `:9101`. Prometheus must
  scrape every replica, not the Compose service DNS name (which load-balances
  one target). Add per-replica targets or use Docker/Consul service discovery.

## 6. Observability

### Metrics

The API exposes the default Prometheus registry at `/metrics`; the worker
aggregates prefork children through `PROMETHEUS_MULTIPROC_DIR` and serves them
on `WORKER_METRICS_PORT` (default 9101). Both scrape targets are configured in
`deploy/prometheus/prometheus.yml`.

Required series:

| Series | Meaning |
|---|---|
| `scrapeflow_http_requests_total{method,route,status}` | API traffic; `route` is the router template |
| `scrapeflow_http_request_duration_seconds` | API latency histogram |
| `scrapeflow_jobs_total{kind,status}` | Terminal jobs |
| `scrapeflow_job_failures_total{kind,code}` | Terminal failures by typed error code |
| `scrapeflow_job_duration_seconds{kind,status}` | Claim-to-terminal duration |
| `scrapeflow_queue_depth{queue}` | Celery queue depth sampled at scrape time |
| `scrapeflow_active_browser_sessions` | Registered browser sessions |
| `scrapeflow_webhook_deliveries_total{event,result}` | Webhook attempts |
| `scrapeflow_webhook_pending` | Due/backed-up deliveries |
| `scrapeflow_quota_rejections_total{reason}` | Plan-limit rejections |
| `scrapeflow_rate_limit_hits_total{scope}` | 429s by limiter |
| `scrapeflow_db_latency_seconds` | Readiness DB query latency |
| `scrapeflow_redis_latency_seconds` | Redis PING latency |

`/metrics` sampling has a readiness timeout and leaves the last gauge values
when the database or Redis is slow; a scrape failure is logged as
`metrics.runtime_sample_failed` and does not affect job traffic.

Load the Grafana dashboard from `deploy/grafana/` (data source and dashboard
providers included) and alert rules from `deploy/prometheus/alerts.yml`.

### Logs

Every API access log is JSON on stdout and includes `request_id`, `method`,
`path`, `status`, `duration_ms`, and `client_ip`. Worker logs bind `job_id` for
the full execution and post-terminal hooks. Do not add secrets, tokens, or full
URLs with credentials to log context.

Useful queries:

```bash
# one request by id
docker compose --project-directory . -f deploy/compose.prod.yml logs api | grep '"request_id":"<id>"'
# one job across API/worker/beat
docker compose --project-directory . -f deploy/compose.prod.yml logs worker beat | grep '"job_id":"<id>"'
```

### Sentry

Set `SENTRY_DSN`; the API initialises Sentry with `send_default_pii=False`,
environment, release, and a 5% trace sample in production. Never attach request
bodies or headers containing API keys.

### Load test

Run on staging, never production:

```bash
LOAD_API_KEY=sf_live_... LOAD_TARGET_URL=https://example.com \
  uv run --group e2e locust -f tests/load/locustfile.py \
  --host https://staging.example.com --users 25 --spawn-rate 5 --run-time 5m --headless
```

Watch p95 latency, 5xx ratio, queue depth, job failure rate, and DB/Redis
latency. Scale workers or Grid nodes until the target concurrency stays under
the plan and infrastructure limits.

## 7. Incident response

1. **Declare and scope.** Check `up{job=~"scrapeflow-.*"}`, `/ready`, and
   recent deploy/image tags.
2. **Stabilise.** Roll back the last image if the error budget is burning.
   Pause non-critical load (`docker compose ... stop beat` if schedules are
   amplifying an incident), never pause the API's health checks.
3. **Diagnose.** Correlate a failing `request_id` with the worker `job_id`.
   Check `scrapeflow_job_failures_total` by code and webhook pending count.
4. **Communicate.** Status page: API/dashboard availability, queued job delay,
   webhook delay, affected regions/proxies.
5. **Recover.** Requeue stuck jobs with the reaper; replay webhook DLQ entries
   only after the endpoint is healthy. Confirm the outbox drains.
6. **Postmortem.** Record timeline, affected orgs, error codes, and a concrete
   preventive action. Do not paste secrets or customer payloads into tickets.

### Common alerts

| Alert | First checks | Mitigation |
|---|---|---|
| `ScrapeFlowApiDown` | container status, `/ready`, Caddy logs | restart/rollback API; verify DB/Redis |
| `ScrapeFlowWorkerDown` | worker logs, `PROMETHEUS_MULTIPROC_DIR`, port 9101 | restart worker; confirm broker connectivity |
| `ScrapeFlowHighErrorRate` | 5xx by route, Sentry, recent deploy | rollback or disable the failing dependency |
| `ScrapeFlowSlowRequests` | DB latency, Redis latency, queue depth | scale API, investigate slow queries |
| `ScrapeFlowQueueBacklog` | worker count, Grid capacity, job durations | add workers/Grid; shed non-critical schedules |
| `ScrapeFlowHighJobFailureRate` | failure codes, proxy health, Grid | fix proxy/Grid; retry after no mutating step succeeded |
| `ScrapeFlowWebhookBacklog` | endpoint health, DLQ count | pause endpoint, replay after recovery |
| `ScrapeFlowDatabaseLatency` | connections, locks, disk | fail over/scale; reduce pool pressure |
| `ScrapeFlowRedisLatency` | memory, evictions, network | scale Redis; remove large keys |

## 8. Routine checks

- Daily: `/ready`, error budget, queue depth, oldest queued job, webhook DLQ.
- Weekly: certificate expiry, disk usage (Postgres/MinIO/logs), backup success,
  dependency audit (`uv run pip-audit`, `npm audit --omit=dev` in `apps/web`).
- Monthly: restore drill on a disposable DB, rotate API keys, review
  `METRICS_TOKEN` exposure, review Sentry noise.
- Per release: `ruff`, `mypy`, Python tests with PostgreSQL/Redis, web
  lint/typecheck/Vitest/build, Playwright journey, `docker compose config`.

See `docs/security-checklist.md` before every production release.
