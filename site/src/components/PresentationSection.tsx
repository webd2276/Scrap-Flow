import { Download, ExternalLink, FileText } from "lucide-react";
import { Suspense, lazy } from "react";
import { PRESENTATION_FILE, PRESENTATION_PAGES, SECTION_COPY } from "../data/site";
import { assetUrl } from "../lib/asset";
import { useInView } from "../lib/useInView";
import { ErrorBoundary } from "./ErrorBoundary";
import { SectionHeading, SectionShell } from "./Section";

// pdf.js is the heaviest dependency on the site; keep it out of the initial
// bundle and only fetch it when this section scrolls near the viewport.
const PdfViewer = lazy(() =>
  import("./pdf/PdfViewer").then((module) => ({ default: module.PdfViewer })),
);

function ViewerSkeleton() {
  return (
    <div
      className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--panel)] shadow-card"
      role="status"
      aria-label="Loading the presentation viewer"
    >
      <div className="flex items-center gap-2 border-b border-[var(--border)] bg-[var(--bg-soft)]/70 px-3 py-2.5">
        <div className="h-8 w-8 animate-pulse rounded-lg bg-[var(--border)]" />
        <div className="h-4 w-24 animate-pulse rounded bg-[var(--border)]" />
        <div className="ml-auto h-8 w-36 animate-pulse rounded-lg bg-[var(--border)]" />
      </div>
      <div className="p-4">
        <div className="aspect-video w-full animate-pulse rounded-lg border border-[var(--border)] bg-[var(--bg-soft)]" />
      </div>
    </div>
  );
}

function ViewerUnavailable() {
  return (
    <div className="rounded-2xl border border-amber-400/40 bg-[var(--panel)] p-5 shadow-card">
      <p className="text-sm font-bold text-amber-700 dark:text-amber-300">
        The presentation viewer could not be loaded
      </p>
      <p className="mt-1.5 text-sm leading-relaxed text-[var(--muted)]">
        The viewer is a separate download. The deck itself is still available.
      </p>
      <div className="mt-4 flex flex-wrap gap-3">
        <a href={assetUrl(PRESENTATION_FILE)} download={PRESENTATION_FILE} className="btn-primary">
          <Download aria-hidden="true" className="h-4 w-4" />
          Download PDF
        </a>
        <a
          href={assetUrl(PRESENTATION_FILE)}
          target="_blank"
          rel="noopener noreferrer"
          className="btn-ghost"
        >
          <ExternalLink aria-hidden="true" className="h-4 w-4" />
          Open in new tab
        </a>
      </div>
    </div>
  );
}

export function PresentationSection() {
  const [viewerRef, inView] = useInView<HTMLDivElement>({
    once: true,
    rootMargin: "420px",
    threshold: 0.01,
  });

  return (
    <SectionShell id="presentation">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <SectionHeading
          eyebrow={SECTION_COPY.presentation.eyebrow}
          title={SECTION_COPY.presentation.title}
          lead={SECTION_COPY.presentation.lead}
        />
        <a
          href={assetUrl(PRESENTATION_FILE)}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex shrink-0 items-center gap-2 text-sm font-semibold text-[var(--accent-2)] hover:underline"
        >
          <FileText aria-hidden="true" className="h-4 w-4" />
          {PRESENTATION_FILE.replace(/-/g, " ")} · {PRESENTATION_PAGES} pages
        </a>
      </div>

      <div ref={viewerRef} className="mt-10 min-h-[320px]">
        {inView ? (
          <ErrorBoundary fallback={<ViewerUnavailable />}>
            <Suspense fallback={<ViewerSkeleton />}>
              <PdfViewer />
            </Suspense>
          </ErrorBoundary>
        ) : (
          <ViewerSkeleton />
        )}
      </div>
    </SectionShell>
  );
}
