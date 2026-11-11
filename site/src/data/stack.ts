export interface StackRow {
  layer: string;
  technology: string;
  version: string;
  role: string;
}

export interface StackTab {
  id: string;
  label: string;
  rows: StackRow[];
  note?: string;
}

export const STACK_TABS: readonly StackTab[] = [
  {
    id: "backend",
    label: "Backend",
    rows: [
      { layer: "API", technology: "FastAPI", version: "0.162", role: "HTTP routing, dependency injection and OpenAPI" },
      { layer: "ASGI", technology: "Starlette", version: "1.10", role: "ASGI toolkit and middleware" },
      { layer: "Server", technology: "Uvicorn", version: "0.32", role: "ASGI server in the API container" },
      { layer: "Validation", technology: "Pydantic", version: "v2", role: "Request, response and settings models" },
      { layer: "ORM", technology: "SQLAlchemy", version: "2 (async)", role: "Async sessions and typed models" },
      { layer: "Driver", technology: "asyncpg", version: "0.30", role: "PostgreSQL driver for async SQLAlchemy" },
      { layer: "Migrations", technology: "Alembic", version: "1.14", role: "Schema revisions run by the migrate service" },
      { layer: "Database", technology: "PostgreSQL", version: "16", role: "Tenants, jobs, billing, schedules, webhooks" },
      { layer: "Queue", technology: "Celery", version: "5.4", role: "Job execution, Beat schedules and maintenance" },
      { layer: "Redis client", technology: "redis-py", version: "5.2", role: "Broker, rate limits, quotas and secrets TTL" },
      { layer: "Scheduling", technology: "croniter", version: "3.0", role: "Cron parsing for user schedules" },
      { layer: "HTTP client", technology: "httpx", version: "0.27", role: "Outbound fetches, webhooks and Stripe calls" },
      { layer: "HTML parsing", technology: "parsel", version: "1.9", role: "CSS and XPath extraction" },
      { layer: "Browser", technology: "Selenium", version: "4.25", role: "Remote Chrome sessions on Selenium Grid" },
      { layer: "Storage SDK", technology: "boto3", version: "—", role: "S3-compatible artifact upload and presigning" },
      { layer: "Auth", technology: "PyJWT", version: "2.9", role: "HS256 access tokens and claim validation" },
      { layer: "Passwords", technology: "argon2-cffi", version: "—", role: "Argon2id password hashing" },
      { layer: "Crypto", technology: "cryptography", version: "—", role: "AES-GCM secret sealing and HMAC helpers" },
      { layer: "Logging", technology: "structlog", version: "—", role: "JSON logs with request and job ids" },
      { layer: "Metrics", technology: "prometheus-client", version: "—", role: "Queue, latency and webhook metrics" },
      { layer: "Errors", technology: "sentry-sdk", version: "—", role: "Optional exception reporting" },
      { layer: "Billing", technology: "Stripe", version: "—", role: "Checkout, portal and signed webhook events" },
    ],
  },
  {
    id: "frontend",
    label: "Frontend",
    rows: [
      { layer: "Framework", technology: "Next.js", version: "16.4.5", role: "Dashboard and same-origin BFF route handlers" },
      { layer: "UI", technology: "React", version: "19.3.1", role: "Client components for the dashboard" },
      { layer: "Language", technology: "TypeScript", version: "5.9.3", role: "Strict types across app and BFF" },
      { layer: "Styles", technology: "Tailwind CSS", version: "4.3.4", role: "Utility styling for the dashboard" },
      { layer: "Lint", technology: "ESLint", version: "9", role: "Static checks in CI" },
      { layer: "Unit tests", technology: "Vitest", version: "—", role: "Client helper and component tests" },
      { layer: "E2E", technology: "Playwright", version: "—", role: "Browser journeys against the running stack" },
    ],
  },
  {
    id: "infra",
    label: "Infra",
    rows: [
      { layer: "Orchestration", technology: "Docker Compose", version: "v2", role: "Dev, test and production topologies" },
      { layer: "Edge", technology: "Caddy", version: "2.8", role: "Automatic TLS and reverse proxy in production" },
      { layer: "Shell", technology: "Bash", version: "3.2+", role: "Linux and macOS runners" },
      { layer: "Windows", technology: "PowerShell", version: "5.1+", role: "Native Windows runner" },
      { layer: "Python packages", technology: "uv", version: "0.13+", role: "Locked dependency installs and command runner" },
      { layer: "Node packages", technology: "npm", version: "10+ (Node 22)", role: "Dashboard dependency installs and builds" },
    ],
    note: "Versions are the ones recorded by the project's lockfiles and SETUP.md. Where a library version is not pinned in the documentation, the row shows a dash rather than guessing.",
  },
];
