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
