export interface ArchitectureLayer {
  id: string;
  label: string;
  title: string;
  items: string[];
  accent: string;
}

export const LAYERS: readonly ArchitectureLayer[] = [
  {
    id: "clients",
    label: "Clients",
    title: "Who asks for work",
    items: ["Next.js dashboard", "API consumers", "Celery Beat"],
    accent: "from-indigo-400/70 to-indigo-500/10",
  },
  {
    id: "control",
    label: "Control plane",
    title: "Validate, persist, enqueue",
    items: ["Next.js same-origin BFF", "FastAPI that never launches Chrome"],
    accent: "from-violet-400/70 to-violet-500/10",
  },
  {
    id: "state",
    label: "Durable state",
    title: "The source of truth",
    items: ["PostgreSQL 16", "Redis 7", "S3 / MinIO"],
    accent: "from-sky-400/70 to-sky-500/10",
  },
  {
    id: "execution",
    label: "Async execution",
    title: "Slow work, isolated",
    items: ["Celery worker", "Celery Beat"],
    accent: "from-cyan-400/70 to-cyan-500/10",
  },
  {
    id: "egress",
    label: "Egress",
    title: "One checked way out",
    items: ["httpx + parsel", "Selenium Grid", "Validating egress proxy with IP pinning"],
    accent: "from-emerald-400/70 to-emerald-500/10",
  },
];

export interface LifecycleStep {
  title: string;
  body: string;
}

export const LIFECYCLE: readonly LifecycleStep[] = [
  {
    title: "Authenticate",
    body: "A JWT or a scoped API key resolves to an organization, role and scope set.",
  },
  {
    title: "Validate",
    body: "Pydantic checks the request shape, lengths, URL scheme and automation steps.",
  },
  {
    title: "SSRF pre-check & quota",
    body: "The URL is resolved and rejected if it points at a private range; credits are reserved.",
  },
  {
    title: "Persist & enqueue (202)",
    body: "The job row commits, the payload is sealed where needed, and Celery receives the id.",
  },
  {
    title: "Execute",
    body: "A worker re-reads the payload and fetches over HTTP or drives Chrome on the Grid.",
  },
  {
    title: "Extract",
    body: "Selectors and extraction steps turn the page into typed JSON.",
  },
  {
    title: "Store artifacts",
    body: "Screenshots, HTML and JSON are written to S3-compatible storage with hashes.",
  },
  {
    title: "Finalise",
    body: "Status, duration, usage and errors are committed; quotas are reconciled.",
  },
  {
    title: "Consume",
    body: "The dashboard polls the job, downloads presigned artifacts and fires signed webhooks.",
  },
];
