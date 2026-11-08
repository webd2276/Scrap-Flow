# ScrapeFlow security checklist

Status as of Phase 9. `Verified` means exercised by a test or a local command on
this host; `Unverified` means the control exists but the live third-party path
could not be exercised. Re-review this list before every production release.

## Tenancy and authorization

- [x] Every tenant-owned table carries `org_id`; queries filter by the
  authenticated organisation. Cross-org reads return 404, not 403.
  `packages/core/models.py`, `apps/api/deps.py`, integration tests.
- [x] Roles and scopes are enforced per route; scope checks cannot be bypassed
  with an API key or JWT alone. `packages/core/scopes.py`, `apps/api/deps.py`.
- [x] JWT access tokens are short-lived, refresh tokens rotate and are stored
  hashed; signing keys support `kid` rotation. `packages/core/security/tokens.py`.
- [x] API keys are shown once, stored as a peppered hash, and revoked keys stop
  working immediately. `packages/core/security/api_keys.py`.
- [x] Signup requires ToS acceptance and rejects duplicate emails. Integration
  tests cover the duplicate and missing-ToS paths.

## Secrets

- [x] Required secrets have no defaults and must be 32+ characters; startup
  fails closed. `packages/core/settings.py`.
- [x] Provider/Stripe/webhook credentials use `SecretStr` and are redacted from
  `repr` and logs. `packages/core/proxies.py`, `packages/core/webhooks.py`.
- [x] Automation secrets are sealed with AES-256-GCM bound to the job id, live
  in Redis only for the execution, and are deleted in `finally`.
  `packages/core/secretbox.py`, `apps/worker/tasks/jobs.py`.
- [x] Webhook signing secrets are encrypted at rest with a key derived from
  `WEBHOOK_SECRET_KEY` and returned only once.
  `packages/core/webhooks.py`, `packages/core/secretbox.py`.
- [x] Access logs, job events, results, and errors exclude credentials and
  request bodies. Searches for raw secrets in logs are part of the test suite.
- [ ] Rotate `API_KEY_PEPPER` only with a planned re-issue of all API keys;
  there is no online pepper rotation.
- [ ] `SENTRY_DSN` and `METRICS_TOKEN` are operator secrets; do not commit them.

## SSRF and egress

- [x] Every destination is resolved and checked at connection time; private,
  loopback, link-local, multicast, and metadata addresses are denied.
  `packages/core/ssrf.py`, `apps/worker/egress_proxy`.
- [x] DNS rebinding is mitigated by resolving once, validating every answer,
  and pinning the connection to the validated IP.
- [x] Browser traffic and webhook/HTTP fetches leave through the validating
  egress proxy; the API never launches Chrome and the worker cannot bypass the
  proxy. Browser jobs fail closed without a proxy.
- [x] Redirects are revalidated (or disabled) on the HTTP and webhook paths;
  response bodies are capped.
- [x] `proxy_country` is validated against the configured provider and upstream
  proxies chain behind the validating proxy, so provider URLs never replace
  destination checks. `apps/worker/proxies.py`.
- [x] Robots.txt and AUP domain rules apply to scrape/automation jobs.
  `packages/core/checks.py`, worker scrape path.
- [x] Webhook endpoints must be HTTPS and are revalidated before every delivery.
- [ ] TCP-only proxy health probes do not prove a proxy's egress policy or that
  its credentials are accepted.

## Input validation and abuse limits

- [x] Request schemas reject unknown fields and enforce bounded selectors,
  headers, steps, credentials, URLs, and timeouts. `apps/api/schemas/`.
- [x] Automation uses a discriminated union, not free-form dictionaries.
  `apps/api/schemas/automation.py`.
- [x] Rate limits are atomic Redis token buckets per IP and per organisation,
  with `Retry-After` and `X-RateLimit-*` headers. `packages/core/rate_limit.py`.
- [x] Plan quotas enforce concurrency and monthly credits, returning 429/402
  with headers; quota rejections are metered.
  `apps/api/services/quota.py`, `packages/core/quota.py`.
- [x] `Idempotency-Key` deduplicates job creation per organisation.
- [x] Hard wall-clock job timeouts and an orphan-session reaper prevent runaway
  browser use. `apps/worker/tasks/reaper.py`.
- [x] Exports neutralise spreadsheet formula injection and stream large files.
  `packages/core/exporting.py`.

## Artifacts and downloads

- [x] Artifact storage keys are server-generated, traversal-checked, and scoped
  to `org/job`; downloads require tenant auth.
- [x] S3/MinIO downloads use short-lived presigned redirects; the local backend
  sends `attachment`, `nosniff`, and a sandbox CSP.
- [x] Artifacts expire by plan retention through a beat task.

## Dashboard (apps/web)

- [x] The refresh token lives in an httpOnly, `SameSite=Lax` cookie (Secure in
  production); the access token lives in React memory only.
- [x] The browser never receives the API origin; `/api/proxy/[...path]` accepts
  only `/v1` paths and forwards an allowlisted header set.
- [x] Billing redirects must be HTTPS and download filenames are reduced to a
  safe basename.
- [x] No heavy UI framework; controls have accessible labels.
- [x] Web lint, typecheck, Vitest, production build, and a Chromium Playwright
  journey pass locally.

## Transport and deployment

- [x] Caddy terminates TLS, sends HSTS, and only Caddy publishes ports in the
  production compose file. `deploy/Caddyfile`, `deploy/compose.prod.yml`.
- [x] Containers run as non-root where supported, with `cap_drop: ALL`,
  `no-new-privileges`, read-only root filesystems, and tmpfs.
- [x] CORS is an explicit allowlist; credentials are not wildcarded.
- [x] `/docs` and OpenAPI UI are disabled in production.
- [x] `/metrics` supports `Authorization: Bearer $METRICS_TOKEN` and returns 404
  when metrics are disabled, so the endpoint can be hidden entirely.
- [x] Compose files render with `docker compose config`; images were built and
  the web image served `/login` from a read-only container.
- [ ] A full `docker compose up` is still **Unverified** on this host.

## Dependencies and CI

- [x] Python dependencies are pinned in `uv.lock`; CI runs `pip-audit`.
- [x] Web dependencies are pinned in `package-lock.json`; CI runs `npm ci` and
  builds from the lockfile.
- [x] CI runs ruff, ruff format, mypy, unit tests, integration tests with
  PostgreSQL/Redis, the web gates, and both image builds.
- [x] The load script is repository-owned, requires a dedicated staging key, and
  is not run against production.

## Logging and monitoring

- [x] JSON logs carry `request_id` on every API request and `job_id` for the
  full worker execution, enabling correlation without customer payloads.
- [x] Sentry is initialised with `send_default_pii=False` and a small trace
  sample in production.
- [x] Metrics cover request rate/latency/status, job duration/failures, queue
  depth, active sessions, webhook delivery/backlog, quota rejections,
  rate-limit hits, and DB/Redis latency.
- [x] Alert rules cover API/worker down, error rate, latency, backlog, job
  failure rate, webhook backlog, and dependency latency.
- [x] The runbook covers deploy, rollback, backup/restore, scaling, incidents,
  and routine checks.

## Residual risks to accept explicitly

1. Commercial proxy gateway credentials, live Stripe checkout, Selenium Grid,
   MinIO/S3, live Celery Beat, and a real external webhook receiver remain
   **Unverified** without credentials/Docker infrastructure.
2. Proxy health is TCP-only and cannot attest to egress policy.
3. The load test provides a repeatable profile, not a production capacity
   number; capacity must be measured on the target infrastructure.
4. A compromised operator account with `WEBHOOK_SECRET_KEY` and database access
   can decrypt webhook signing secrets; key custody is outside the app.
5. Browser fingerprinting/stealth and CAPTCHA solving are intentionally not
   implemented; sites may block automation for reasons outside this checklist.
