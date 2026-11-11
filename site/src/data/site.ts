export const REPO_URL = "https://github.com/webd2276/Scrap-Flow";
export const REPO_NAME = "webd2276/Scrap-Flow";
export const PRESENTATION_FILE = "ScrapeFlow-Project-Presentation.pdf";
export const PRESENTATION_PAGES = 37;

export interface NavLink {
  id: string;
  label: string;
}

export const NAV_LINKS: readonly NavLink[] = [
  { id: "overview", label: "Overview" },
  { id: "features", label: "Features" },
  { id: "architecture", label: "Architecture" },
  { id: "stack", label: "Tech Stack" },
  { id: "setup", label: "Setup" },
  { id: "presentation", label: "Presentation" },
  { id: "verified", label: "Verified Scope" },
];

export const SECTION_IDS: readonly string[] = NAV_LINKS.map((link) => link.id);

export const HERO = {
  eyebrow: "Open source · FastAPI + Celery + Selenium Grid",
  title: "ScrapeFlow",
  subtitle:
    "A production-shaped, multi-tenant web scraping & browser-automation platform: durable job queue, real headless browser path, SSRF-safe egress, tenant isolation and artifact storage.",
  chips: [
    "Python 3.12",
    "FastAPI",
    "Celery + Redis",
    "PostgreSQL 16",
    "Selenium Grid",
    "S3 artifacts",
    "Next.js 16",
    "React 19",
    "TypeScript",
  ],
  terminal: {
    command: "$ ./scripts/run.sh",
    ready: "✔ API ready · dashboard up",
  },
} as const;

export interface Stat {
  value: number;
  decimals?: number;
  suffix?: string;
  label: string;
}

export const STATS: readonly Stat[] = [
  { value: 11, label: "services in dev" },
  { value: 29, label: "API routes" },
  { value: 322, label: "tests passing" },
  { value: 15, label: "DB models" },
  { value: 83.08, decimals: 2, suffix: "%", label: "coverage" },
];

export interface RealityCard {
  title: string;
  body: string;
}

export const OVERVIEW = {
  eyebrow: "Why it exists",
  heading: "Scraping is easy to demo and hard to operate.",
  cards: [
    {
      title: "Real browser needed",
      body: "Some pages only exist after JavaScript runs. A plain HTTP client returns a shell, not the content.",
    },
    {
      title: "Long jobs cannot live in a request",
      body: "Scraping and automation outlive an HTTP timeout. A request must return before the work finishes.",
    },
    {
      title: "User URLs are an attack surface",
      body: "SSRF, DNS rebinding and redirects turn a fetch into a path into your own network.",
    },
    {
      title: "Multi-tenancy is not optional",
      body: "Jobs, artifacts, keys and quotas must never leak across organizations.",
    },
  ] satisfies RealityCard[],
  solution:
    "One control plane. One queue. One dashboard. The API returns 202 Accepted and slow work runs in isolated workers.",
} as const;

export type FeatureIcon =
  | "globe"
  | "browser"
  | "schedule"
  | "artifacts"
  | "webhook"
  | "tenancy"
  | "billing"
  | "observability";

export interface Feature {
  icon: FeatureIcon;
  title: string;
  body: string;
}

export const FEATURES: readonly Feature[] = [
  {
    icon: "globe",
    title: "Scrape API",
    body: "CSS selectors over plain HTTP or a rendered browser, with typed errors, timeouts and a hard byte cap.",
  },
  {
    icon: "browser",
    title: "Browser Automation",
    body: "Typed steps: goto, click, type, wait, extract and screenshot, executed by workers on Selenium Grid.",
  },
  {
    icon: "schedule",
    title: "Schedules",
    body: "Cron and timezone aware schedules with run history and a manual trigger for testing.",
  },
  {
    icon: "artifacts",
    title: "Artifacts",
    body: "Screenshots, HTML and JSON stored in S3-compatible storage with presigned downloads, SHA-256 and plan retention.",
  },
  {
    icon: "webhook",
    title: "Signed Webhooks",
    body: "A durable outbox with HMAC signatures, exponential retries and dead-lettering when a receiver is down.",
  },
  {
    icon: "tenancy",
    title: "Tenancy & Quotas",
    body: "Every job, artifact and delivery is org-scoped, with atomic Redis quotas and plan limits.",
  },
  {
    icon: "billing",
    title: "Billing",
    body: "Stripe checkout and portal wiring with plan quotas, disabled by default until real keys are configured.",
  },
  {
    icon: "observability",
    title: "Observability",
    body: "JSON logs with request and job IDs, Prometheus metrics, Sentry hooks, /health and /ready probes.",
  },
] as const;

export interface SecurityCard {
  icon: "shield" | "key" | "fingerprint" | "lock" | "gauge" | "cookie";
  title: string;
  body: string;
}

export const SECURITY: readonly SecurityCard[] = [
  {
    icon: "shield",
    title: "SSRF-safe validating proxy",
    body: "Every outbound hop is resolved, checked against private ranges and pinned to the validated IP.",
  },
  {
    icon: "key",
    title: "JWT access + rotating refresh",
    body: "Short-lived access tokens and hashed, rotated refresh tokens with reuse revocation.",
  },
  {
    icon: "fingerprint",
    title: "Peppered API keys",
    body: "Only a prefix and a peppered hash are stored. The plaintext sf_live_ key is shown once.",
  },
  {
    icon: "lock",
    title: "Encrypted webhook secrets",
    body: "Per-organization signing secrets are sealed with AES-GCM under a separate key.",
  },
  {
    icon: "gauge",
    title: "Atomic quotas and rate limits",
    body: "Redis token buckets and plan quotas fail closed instead of silently letting traffic through.",
  },
  {
    icon: "cookie",
    title: "Same-origin BFF",
    body: "The dashboard keeps the refresh token in an httpOnly cookie and the access token in memory.",
  },
] as const;

export const STRIX_NOTE =
  "Strix, an autonomous AI pentester, is wired as an optional workflow and per-platform runner. It is not in the PR gate, needs an LLM key, and no real scan has run yet — treat it as unverified.";

export const VERIFIED = {
  heading: "Verified vs unverified",
  lead: "What this project can prove, and what still needs a real external service.",
  verified: [
    "Dev Compose stack with 11 services",
    "Real browser scrape via Selenium Grid with screenshot, HTML and JSON artifacts",
    "Presigned artifact download",
    "JWT auth and dashboard session",
    "Celery Beat, reaper, retention and worker metrics",
    "322 Python tests at 83.08% coverage, plus Ruff and mypy",
    "30 Vitest tests, lint, typecheck and production build",
    "Playwright E2E: 5 passed, 2 skipped",
  ],
  unverified: [
    "Live Stripe checkout and portal",
    "Official MinIO image and lifecycle rules",
    "Production Caddy topology",
    "Commercial proxy gateway",
    "Real external webhook receiver",
    "Hosted GitHub Actions run",
    "Locust capacity numbers",
    "Native Windows PowerShell 5.1 / native macOS runs",
    "Strix pentest run",
  ],
} as const;

export interface SectionCopy {
  eyebrow: string;
  title: string;
  lead?: string;
}

/** Shared section intros, so headings and leads are editable as data. */
export const SECTION_COPY = {
  features: {
    eyebrow: "Capabilities",
    title: "Eight pieces that make scraping operable",
    lead: "The platform is deliberately split: validation and state live in the API, execution lives in workers, and every outbound request goes through one checked path.",
  },
  architecture: {
    eyebrow: "System design",
    title: "Five layers, one checked way out",
    lead: "The API never launches Chrome. Slow work leaves the request path, and every browser or HTTP fetch crosses the validating egress boundary.",
  },
  stack: {
    eyebrow: "Technology",
    title: "The stack, layer by layer",
    lead: "Every version below comes from the project's lockfiles or SETUP.md. A dash means the documentation does not pin a version; nothing here is guessed.",
  },
  setup: {
    eyebrow: "Setup & installation",
    title: "From a fresh clone to a running stack",
    lead: "Every step from SETUP.md: one-command runners for four platforms, manual Docker, configuration, tests, production, and the 17-row troubleshooting table.",
  },
  security: {
    eyebrow: "Security highlights",
    title: "Security is a set of boundaries, not a badge",
    lead: "These are the controls the code actually implements. They reduce risk; they do not make the platform automatically safe.",
  },
  presentation: {
    eyebrow: "Project deck",
    title: "The 37-page presentation, in the browser",
    lead: "A 16:9 deck covering the problem, the architecture, the security model and the verified scope. Navigate with the buttons, the page field, or the arrow keys.",
  },
  verified: {
    eyebrow: "Honest scope",
    title: VERIFIED.heading,
    lead: VERIFIED.lead,
  },
  screenshots: {
    eyebrow: "Product",
    title: "The dashboard, as captured",
    lead: "Screenshots from the running Compose stack. If an image is not bundled, the card shows a labelled placeholder instead of a broken frame.",
  },
  faq: {
    eyebrow: "Questions",
    title: "The short answers",
    lead: "If something here contradicts SETUP.md, the guide wins.",
  },
} satisfies Record<string, SectionCopy>;

export interface Screenshot {
  slug: string;
  title: string;
  blurb: string;
  file: string;
}

export const SCREENSHOTS: readonly Screenshot[] = [
  {
    slug: "jobs",
    title: "Jobs list",
    blurb: "Queued, running and finished jobs with status and duration.",
    file: "screenshots/jobs.png",
  },
  {
    slug: "scrape",
    title: "New scrape builder",
    blurb: "URL, selectors, rendering options and artifact toggles.",
    file: "screenshots/scrape.png",
  },
  {
    slug: "automate",
    title: "Automation builder",
    blurb: "Ordered browser steps with screenshots and extraction.",
    file: "screenshots/automate.png",
  },
  {
    slug: "schedules",
    title: "Schedules",
    blurb: "Cron expressions, timezones and recent run history.",
    file: "screenshots/schedules.png",
  },
  {
    slug: "api-keys",
    title: "API keys",
    blurb: "Scoped keys with expiration, shown once at creation.",
    file: "screenshots/api-keys.png",
  },
  {
    slug: "billing",
    title: "Billing",
    blurb: "Plans, quotas and Stripe checkout when billing is enabled.",
    file: "screenshots/billing.png",
  },
];

export interface FaqItem {
  question: string;
  answer: string;
}

export const FAQ: readonly FaqItem[] = [
  {
    question: "What is ScrapeFlow?",
    answer:
      "A multi-tenant scraping and browser-automation platform. FastAPI accepts jobs, Celery workers execute them through a validating egress path or Selenium Grid, and results land in PostgreSQL, Redis and S3-compatible storage. A Next.js dashboard talks to the API through a same-origin BFF.",
  },
  {
    question: "Do I need Docker?",
    answer:
      "For the fastest path, yes: Docker Engine 24+ or Docker Desktop with Compose v2. One runner script builds the images, creates .env with random secrets and waits for /ready. A manual local path with uv, Node and two containers is documented for development without the full stack.",
  },
  {
    question: "Is Stripe required?",
    answer:
      "No. Billing is off by default with BILLING_ENABLED=false, and the plan/quota system works without Stripe. Checkout and the customer portal only activate once real Stripe keys and price IDs are configured.",
  },
  {
    question: "Why is the API not launching Chrome?",
    answer:
      "Browser execution is deliberately worker-only. The API validates, persists and enqueues; workers own Selenium and the egress proxy, which is what keeps a slow or hostile page from occupying the request path and keeps SSRF enforcement in one place.",
  },
  {
    question: "What is unverified?",
    answer:
      "Anything that needs an external service or a different operating system: live Stripe, the official MinIO image and lifecycle rules, the production Caddy topology, a commercial proxy gateway, a real webhook receiver, hosted CI, Locust capacity numbers, native Windows PowerShell 5.1 and macOS runs, and a real Strix scan. The site labels those paths instead of claiming they work.",
  },
];

export const FOOTER = {
  tagline: "Documentation site for ScrapeFlow.",
  note: "Static site — no backend, no database, no tracking.",
} as const;
