# Architecture decisions

Each entry: decision, alternatives, reason. Newer decisions win; do not silently
edit history.

## D-001 — Celery 5 with Redis broker; Postgres is the status source
Alternatives: Arq, RQ, custom.
Reason: mature Beat/retry/operability story, no need for a second result backend.
Celery carries only `job_id`; all durable state is in Postgres.

## D-002 — S3-compatible object storage for artifacts
Alternatives: Postgres bytea, local disk.
Reason: screenshots/HTML must not bloat the DB or API memory; MinIO in dev, any S3 in prod.

## D-003 — Connection-time egress proxy in front of Selenium Grid
Alternatives: application URL checks only, DNS pinning in Chrome only.
Reason: page JavaScript ignores application checks; a validating proxy sees and denies
every destination at connect time.

## D-004 — `render_js=true` uses the browser; `false` uses an SSRF-safe HTTP fetch
Alternatives: always browser, reject false.
Reason: the flag must mean something; static pages are cheaper over HTTP. Both paths use
the same URL validator and per-hop redirect checks.

## D-005 — New organisations respect robots.txt by default
Alternatives: default off, no enforcement.
Reason: legal safety. Opt-out requires accepting the acceptable-use policy and is audited.

## D-006 — Reserve credits at job acceptance; refund only before navigation
Alternatives: charge on completion.
Reason: prevents free concurrency abuse and gives deterministic quota headers. Failed
jobs that never opened a browser are refunded.

## D-007 — Email notifications are optional; webhooks are mandatory
Alternatives: require SMTP, fake email.
Reason: no provider is specified. Without SMTP the change is still recorded and the
delivery is marked `email_skipped`.

## D-008 — Unsupported `proxy_country` is a 422
Alternatives: silently ignore.
Reason: never silently drop a paid feature.

## D-009 — API keys: `sf_live_<prefix>_<secret>`, SHA-256 + server pepper
Alternatives: bcrypt/argon2 for high-entropy keys.
Reason: high-entropy keys do not need a slow KDF; prefix lookup plus constant-time
compare keeps verification cheap and safe.

## D-010 — Artifact retention by plan, purged nightly
Alternatives: retain forever.
Reason: privacy and storage cost; retention is part of the plan contract.

## D-011 — Restructure to `apps/` + `packages/` now
Alternatives: keep flat `app/`.
Reason: the spec fixes the layout; the old tree is retained in git history.

## D-012 — Typed `ErrorCode` enum maps to HTTP status
Alternatives: free-form strings.
Reason: stable client contract and metrics dimensions.

## D-013 — Local fallbacks when Docker is unavailable
Alternatives: skip verification.
Reason: user-space PostgreSQL/Redis/Chrome still exercise real code; CI remains the
authority for pinned Postgres 16/Redis 7/Grid.

## D-014 — Strict startup settings, no secret defaults
Alternatives: development defaults.
Reason: fail fast, never ship placeholder credentials. Tests inject `Settings` directly.

## D-015 — JWT signing key rotation via `kid`
Alternatives: single secret with no identifier.
Reason: `kid` lets a new secret become active while old access tokens still verify.
`JWT_ACTIVE_KID` names the signing key; `JWT_PREVIOUS_KEYS` is a JSON map of
retired kid → secret. The keyring is validated at startup.

## D-016 — Refresh-token reuse revokes the whole family
Alternatives: return 401 for the replayed token only.
Reason: a rotated token presented again indicates theft; leaving the newly
issued token valid lets attacker and victim both keep sessions. Reuse revokes
every active refresh token for that user.

## D-017 — API keys may only mint a subset of their own scopes
Alternatives: any `keys:manage` key can mint `*`.
Reason: otherwise a limited key escalates itself to billing/audit/admin. JWTs
for owners/admins carry `*`; API keys are checked against their held scopes.

## D-018 — One-shot migration service; trusted proxy only on internal network
Alternatives: run Alembic in the API command or manually.
Reason: a dedicated `migrate` service makes deploy ordering explicit and avoids
replica races. In production the API is not published; Caddy is the only
ingress, so uvicorn may trust `X-Forwarded-For` from the compose network for
per-IP limits. The development compose publishes the API directly and does not
trust forwarded headers.

## D-019 — PostgreSQL is the job source of truth; Redis is only a broker
Alternatives: trust the broker for job state.
Reason: enqueue can fail after the API commits. A dedicated reaper requeues
stale `queued` rows and expires `running` leases, so acceptance is durable even
when Redis blips. `attempts`/`max_attempts` bound retries, and a lost worker is
reported as `WORKER_LOST` instead of silently dropping the job.

## D-020 — Two independent SSRF checks, with a pinned connection
Alternatives: validate once in the API and let httpx/Chrome resolve again.
Reason: DNS can change between validation and connection (rebinding). The API
validates before accepting work; the egress proxy resolves again at connection
time and connects to the checked literal IP. HTTP redirects are validated per
hop, and browser jobs re-validate the final URL. The proxy is the only egress
path in compose, and its allowlist is restricted to `80,443`.

## D-021 — Browsers run only in workers; remote Grid requires the proxy
Alternatives: launch Chrome inside the API or let Grid reach the internet directly.
Reason: the API process stays small and cannot exhaust memory with browsers,
while Grid nodes have no direct egress. A remote Selenium URL without
`EGRESS_PROXY_URL` is refused with `503` rather than silently bypassing checks.

## D-022 — Server-generated artifact keys; presigned redirects with local fallback
Alternatives: accept client filenames/keys.
Reason: user-controlled storage keys enable traversal and cross-tenant reads.
Keys are `org/job/uuid-sanitised-name`, checked for traversal before any local
filesystem call. S3/MinIO responses use a short-lived presigned redirect; the
local backend streams the file with `attachment`, `nosniff`, and `sandbox` CSP.
Retention is plan-driven in later phases; Phase 3 stores `expires_at`.

## D-023 — `screenshot` and `wait_for` require `render_js=true`
Alternatives: silently ignore them on the HTTP path.
Reason: explicit validation avoids a request that appears accepted but cannot
produce the requested output. `proxy_country` is likewise rejected with `422`
until a proxy provider exists (D-008), rather than pretending to route traffic.

## D-024 — MinIO is added to compose, but the image tag is operator-supplied
Alternatives: require Docker Hub `minio/minio`.
Reason: MinIO discontinued its free community images during 2026. Compose uses
`MINIO_IMAGE` with a pinned default and documents that operators must mirror the
image. `scripts/ensure_bucket.py` creates the bucket with the application image,
so no extra `mc` image is required.

## D-025 — Automation secrets live only in sealed Redis blobs
Alternatives: store encrypted values in the job row; keep them in process memory.
Reason: the job payload is visible to every read of `jobs` and to backups. The API
seals the map with AES-256-GCM, using a dedicated `AUTOMATION_SECRET_KEY` or an
HKDF derivation from `JWT_SECRET`, and binds the ciphertext to the job id as
associated data. The worker reads it once, deletes the key in `finally`, and
never writes values to logs or step records. TTL is a backstop if the worker
dies. Placeholder interpolation is limited to `type.text`, `select.value`, and
`press.key`; undeclared placeholders are rejected at submission.

## D-026 — Steps fail closed on unknown fields and explicit optionality
Alternatives: ignore unknown actions/fields for forward compatibility.
Reason: silently ignoring a paid action or a misspelled selector produces a
successful-looking job with missing output. The discriminated union rejects
unknown actions, extra fields, and missing required fields. `optional=true`
records a `skipped` step and continues; otherwise the job fails with a partial
result and a failure screenshot. Retries are bounded per step and only for
transient browser failures.

## D-027 — Automation is browser-only; scrape keeps the HTTP fast path
Alternatives: run automation steps against a parsed DOM without a browser.
Reason: clicks, typing, hover, and navigation require a real browser, and
pretending otherwise would accept jobs the engine cannot execute. Automation
therefore always uses Selenium and the egress proxy; `render_js` is implied.
Static extraction remains a scrape job.

## D-028 — Credits are reserved at acceptance and settled once execution starts
Alternatives: charge only on success, or charge at the end of the request.
Reason: charging on success lets a caller launch unlimited failing work; charging
after execution lets concurrent requests overrun the monthly cap. The API
reserves a deterministic cost inside the acceptance transaction, releases it
only when the job never starts (dispatch failure or pre-start cancellation), and
commits it once a worker begins. Success, failure, timeout, and running
cancellation all consume the reservation because the work was performed.
Reservation and settlement are serialized per organization with a PostgreSQL
advisory lock, so two API replicas cannot both observe the last credit.

## D-029 — Redis is the fast quota counter; `usage_ledger` is the durable record
Alternatives: count credits with `SELECT sum(...)` on every request, or trust
Redis alone.
Reason: a SQL sum on the hot path serializes acceptance, while Redis alone loses
the month on eviction or failover. Lua scripts make reserve/release atomic, and
each accepted job writes a `usage_ledger` row in the same transaction as the job.
A beat task reconciles the Redis counter upward from the ledger and repairs a
cold cache. Reads prefer the ledger when it is ahead, so a lost Redis key cannot
silently grant a fresh quota.

## D-030 — Concurrency is a self-expiring Redis lease, not a database count
Alternatives: count `running` rows in PostgreSQL, or hold a semaphore in memory.
Reason: a crashed worker must not block the organization forever. Each accepted
job adds a member to an org-scoped sorted set with a TTL above the hard job
deadline; the worker and reaper remove it on completion. Membership is keyed by
job id, so acquiring the same job twice is idempotent. The reaper also removes
leases for jobs that no longer exist. PostgreSQL remains the source of truth for
job state, but the lease alone gates admission.

## D-031 — Plan-limit violations return 402; concurrency saturation returns 429
Alternatives: use 403 for both, or hide limits from responses.
Reason: the dashboard needs to distinguish "upgrade your plan" from "retry
shortly". 402 `QUOTA_EXCEEDED` covers exhausted credits and step/page caps, with
`X-Quota-Limit`, `X-Quota-Remaining`, and `X-Quota-Reset`. 429
`CONCURRENCY_LIMIT` covers the in-flight cap and includes `Retry-After` plus
`X-Concurrency-*`. Both are typed errors, so clients never parse prose.

## D-032 — Stripe events are recorded before they are applied
Alternatives: apply first and rely on Stripe's retry window.
Reason: a crash between applying a plan change and recording the event would
double-apply on redelivery. `stripe_events.event_id` is unique; the row is
inserted with `status=processing` before side effects. A duplicate with
`status=processed` returns `duplicate: true`; a `failed` row is retried and
flipped to `processed` on success. Signatures are verified over the raw body with
a bounded timestamp tolerance, and unknown event types are recorded but ignored
rather than failing the endpoint.

## D-033 — Artifact retention is plan-driven on write; the purger is generic
Alternatives: a single deployment-wide retention value, or per-plan S3 buckets.
Reason: `Organization.plan` determines `expires_at` when the artifact row is
written, so upgrading or downgrading a plan affects new artifacts without a data
migration. The beat purger deletes any row past `expires_at` and its object in
bounded batches, which also covers rows left by deleted jobs. Operators may still
add lifecycle rules for defense in depth, but correctness does not depend on
them.

## D-034 — Checkout and portal are operator-configured, not hard-coded
Alternatives: embed price IDs or return URLs in application code.
Reason: price IDs differ between Stripe test and live modes and may change with
pricing experiments. `STRIPE_PRICE_*`, `BILLING_SUCCESS_URL`,
`BILLING_CANCEL_URL`, and `BILLING_PORTAL_RETURN_URL` are settings; a missing
price returns `503 BILLING_ERROR` instead of creating a broken session. Billing
is off by default (`BILLING_ENABLED=false`), while local quota accounting remains
active so development and tests exercise the same admission path.
