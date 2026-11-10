export type ProjectHighlight = {
  label: string;
  value: string;
  context: string;
  status: string;
};

export const projectHighlights: ProjectHighlight[] = [
  {
    label: "Automated checks",
    value: "322 passed · 3 skipped",
    context: "Local verification report, 2026-11-08",
    status: "Reported locally",
  },
  {
    label: "Branch and line coverage",
    value: "83.08%",
    context: "Local verification report, 2026-11-08",
    status: "Reported locally",
  },
  {
    label: "Browser automation",
    value: "Selenium Grid + Celery",
    context: "Documented platform capability",
    status: "Implemented",
  },
  {
    label: "Hosted GitHub Actions run",
    value: "Not observed",
    context: "The report contains no hosted run evidence",
    status: "Unverified",
  },
];

export const platformAreas = [
  {
    area: "API",
    technology: "FastAPI",
    summary: "Control plane for scraping and automation jobs.",
    status: "Implemented",
  },
  {
    area: "Job execution",
    technology: "Celery workers",
    summary: "Background execution for queued work.",
    status: "Implemented",
  },
  {
    area: "Browser path",
    technology: "Selenium Grid",
    summary: "Browser-driven page interaction through a dedicated grid.",
    status: "Implemented",
  },
  {
    area: "Web dashboard",
    technology: "Next.js",
    summary: "User-facing project dashboard.",
    status: "Implemented",
  },
];
