import {
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
  FileWarning,
  Maximize2,
  Minimize2,
  RotateCcw,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { PRESENTATION_FILE, PRESENTATION_PAGES } from "../../data/site";
import { assetUrl } from "../../lib/asset";
import { cn } from "../../lib/cn";
import { useInView } from "../../lib/useInView";

// The worker must be a real URL. Importing it with `?url` lets Vite hash and
// copy it into the build, which also keeps GitHub Pages sub-paths working.
pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

const PDF_URL = assetUrl(PRESENTATION_FILE);
const MIN_ZOOM = 0.6;
const MAX_ZOOM = 2.4;
const ZOOM_STEP = 0.2;

function clampPage(value: number, total: number): number {
  if (!Number.isFinite(value)) {
    return 1;
  }
  return Math.min(total, Math.max(1, Math.trunc(value)));
}

export function PdfViewer() {
  const [shellRef, viewerInView] = useInView<HTMLDivElement>({
    once: false,
    threshold: 0.3,
  });
  const frameRef = useRef<HTMLDivElement>(null);

  const [numPages, setNumPages] = useState(PRESENTATION_PAGES);
  const [page, setPage] = useState(1);
  const [pageField, setPageField] = useState("1");
  const [zoom, setZoom] = useState(1);
  const [frameWidth, setFrameWidth] = useState(0);
  const [failed, setFailed] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  // react-pdf does not mount children until the document is parsed, so the
  // measured frame appears late. Re-run the observer when that happens.
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const node = frameRef.current;
    if (!node || typeof ResizeObserver === "undefined") {
      return;
    }

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setFrameWidth(Math.round(entry.contentRect.width));
      }
    });

    observer.observe(node);
    return () => observer.disconnect();
  }, [loaded]);

  useEffect(() => {
    function onFullscreenChange() {
      setIsFullscreen(document.fullscreenElement === shellRef.current);
    }

    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", onFullscreenChange);
  }, []);

  const goTo = useCallback(
    (next: number) => {
      const target = clampPage(next, numPages);
      setPage(target);
      setPageField(String(target));
    },
    [numPages],
  );

  const changeZoom = useCallback((delta: number) => {
    setZoom((current) => {
      const next = Math.round((current + delta) * 10) / 10;
      return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, next));
    });
  }, []);

  const toggleFullscreen = useCallback(async () => {
    const node = shellRef.current;
    if (!node) {
      return;
    }

    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else if (node.requestFullscreen) {
        await node.requestFullscreen();
      }
    } catch {
      // Fullscreen can be blocked by browser policy; the viewer still works.
    }
  }, []);

  // Arrow keys work while the deck is on screen, even if focus is on the page
  // body. Typing in the page field or any other input is left alone.
  useEffect(() => {
    if (!viewerInView) {
      return;
    }

    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }

      if (event.key === "ArrowRight" || event.key === "PageDown") {
        event.preventDefault();
        goTo(page + 1);
      } else if (event.key === "ArrowLeft" || event.key === "PageUp") {
        event.preventDefault();
        goTo(page - 1);
      } else if (event.key === "Home") {
        event.preventDefault();
        goTo(1);
      } else if (event.key === "End") {
        event.preventDefault();
        goTo(numPages);
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [viewerInView, page, numPages, goTo]);

  function commitPageField() {
    goTo(Number.parseInt(pageField, 10));
  }

  if (failed) {
    return <PdfFallback />;
  }

  const pageWidth = frameWidth > 0 ? Math.round(frameWidth * zoom) : undefined;

  return (
    <div
      ref={shellRef}
      className={cn(
        "overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--panel)] shadow-card",
        isFullscreen && "flex h-full flex-col rounded-none border-0 bg-[var(--bg)]",
      )}
    >
      <div className="flex flex-wrap items-center gap-2 border-b border-[var(--border)] bg-[var(--bg-soft)]/70 px-3 py-2">
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => goTo(page - 1)}
            disabled={page <= 1}
            className="icon-btn !h-8 !w-8 disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="Previous page"
          >
            <ChevronLeft aria-hidden="true" className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => goTo(page + 1)}
            disabled={page >= numPages}
            className="icon-btn !h-8 !w-8 disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="Next page"
          >
            <ChevronRight aria-hidden="true" className="h-4 w-4" />
          </button>
        </div>

        <form
          className="flex items-center gap-1.5"
          onSubmit={(event) => {
            event.preventDefault();
            commitPageField();
          }}
        >
          <label htmlFor="pdf-page" className="sr-only">
            Page number
          </label>
          <input
            id="pdf-page"
            type="text"
            inputMode="numeric"
            value={pageField}
            onChange={(event) => setPageField(event.target.value)}
            onBlur={commitPageField}
            aria-describedby="pdf-page-total"
            className="h-8 w-12 rounded-lg border border-[var(--border)] bg-[var(--panel)] text-center font-mono text-xs text-[var(--text)] focus-visible:outline-none"
          />
          <span
            id="pdf-page-total"
            className="font-mono text-xs text-[var(--muted)]"
            aria-live="polite"
          >
            / {numPages}
          </span>
        </form>

        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            onClick={() => changeZoom(-ZOOM_STEP)}
            disabled={zoom <= MIN_ZOOM}
            className="icon-btn !h-8 !w-8 disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="Zoom out"
          >
            <ZoomOut aria-hidden="true" className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => setZoom(1)}
            className="min-w-[3.25rem] rounded-lg px-1.5 py-1 font-mono text-[11px] text-[var(--muted)] transition hover:bg-[var(--bg-soft)] hover:text-[var(--text)]"
            aria-label={`Reset zoom. Current zoom ${Math.round(zoom * 100)} percent`}
          >
            {Math.round(zoom * 100)}%
          </button>
          <button
            type="button"
            onClick={() => changeZoom(ZOOM_STEP)}
            disabled={zoom >= MAX_ZOOM}
            className="icon-btn !h-8 !w-8 disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="Zoom in"
          >
            <ZoomIn aria-hidden="true" className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => setZoom(1)}
            className="icon-btn !hidden !h-8 !w-8 sm:inline-flex"
            aria-label="Reset zoom to fit"
          >
            <RotateCcw aria-hidden="true" className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={toggleFullscreen}
            className="icon-btn !h-8 !w-8"
            aria-label={isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
          >
            {isFullscreen ? (
              <Minimize2 aria-hidden="true" className="h-4 w-4" />
            ) : (
              <Maximize2 aria-hidden="true" className="h-4 w-4" />
            )}
          </button>
        </div>
      </div>

      <Document
        file={PDF_URL}
        onLoadSuccess={({ numPages: total }) => {
          setNumPages(total);
          setPageField(String(Math.min(page, total)));
          setPage((current) => clampPage(current, total));
          setLoaded(true);
        }}
        onLoadError={() => setFailed(true)}
        loading={
          <div className="p-4">
            <PdfSkeleton />
          </div>
        }
        // `contents` keeps the provider wrapper out of the layout so the frame,
        // footer and thumbnail strip stack as before while sharing one document
        // context (react-pdf pages outside a Document throw an invariant).
        className="contents"
      >
        <div
          ref={frameRef}
          // A focusable region so arrow keys work without a global listener that
          // would hijack typing elsewhere on the page.
          tabIndex={0}
          role="region"
          aria-label="PDF preview. Use arrow keys to change pages."
          className={cn(
            "scroll-slim relative overflow-auto bg-slate-950/60 p-3 sm:p-4",
            isFullscreen ? "flex-1" : "h-[min(78vh,760px)]",
          )}
        >
          <div className="pdf-page flex min-h-full items-start justify-center">
            {frameWidth > 0 ? (
              <Page
                pageNumber={page}
                width={pageWidth}
                renderAnnotationLayer={false}
                renderTextLayer={false}
                loading={<PdfSkeleton />}
                className="overflow-hidden rounded-lg shadow-2xl"
              />
            ) : (
              <PdfSkeleton />
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 border-t border-[var(--border)] px-3 py-2 text-xs text-[var(--muted)]">
          <p className="min-w-0">
            Page {page} of {numPages} · use ← → to navigate
          </p>
          <div className="ml-auto flex items-center gap-2">
            <a
              href={PDF_URL}
              download={PRESENTATION_FILE}
              className="inline-flex items-center gap-1.5 font-semibold text-[var(--accent-2)] hover:underline"
            >
              <Download aria-hidden="true" className="h-3.5 w-3.5" />
              Download
            </a>
            <a
              href={PDF_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 font-semibold text-[var(--accent-2)] hover:underline"
            >
              <ExternalLink aria-hidden="true" className="h-3.5 w-3.5" />
              Open in new tab
            </a>
          </div>
        </div>

        <ThumbnailStrip page={page} numPages={numPages} onSelect={goTo} />
      </Document>
    </div>
  );
}

function ThumbnailStrip({
  page,
  numPages,
  onSelect,
}: {
  page: number;
  numPages: number;
  onSelect: (next: number) => void;
}) {
  const [stripRef, inView] = useInView<HTMLDivElement>({
    once: true,
    rootMargin: "240px",
    threshold: 0.01,
  });

  return (
    <div
      ref={stripRef}
      className="border-t border-[var(--border)] bg-[var(--bg-soft)]/60 px-3 py-3"
    >
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">
        Pages
      </p>
      <div className="scroll-slim flex gap-2 overflow-x-auto pb-1">
        {inView
          ? Array.from({ length: numPages }, (_, index) => index + 1).map((number) => (
              <Thumbnail
                key={number}
                number={number}
                active={number === page}
                onSelect={onSelect}
              />
            ))
          : Array.from({ length: Math.min(numPages, 12) }, (_, index) => (
              <div
                key={index}
                aria-hidden="true"
                className="h-[54px] w-24 shrink-0 animate-pulse rounded border border-[var(--border)] bg-[var(--panel)]"
              />
            ))}
      </div>
    </div>
  );
}

function Thumbnail({
  number,
  active,
  onSelect,
}: {
  number: number;
  active: boolean;
  onSelect: (next: number) => void;
}) {
  const [ref, inView] = useInView<HTMLButtonElement>({
    once: true,
    rootMargin: "320px",
    threshold: 0.01,
  });

  return (
    <button
      ref={ref}
      type="button"
      onClick={() => onSelect(number)}
      aria-label={`Go to page ${number}`}
      aria-current={active ? "page" : undefined}
      className={cn(
        "pdf-thumb relative w-24 shrink-0 overflow-hidden rounded border bg-slate-950/70 transition",
        active
          ? "border-[var(--accent-2)] ring-2 ring-[var(--accent-2)]/40"
          : "border-[var(--border)] hover:border-[var(--border-strong)]",
      )}
    >
      <span className="block aspect-[16/9] w-full">
        {inView ? (
          <Page
            pageNumber={number}
            width={92}
            renderAnnotationLayer={false}
            renderTextLayer={false}
            loading={<span className="block h-full w-full animate-pulse bg-[var(--panel)]" />}
          />
        ) : (
          <span className="block h-full w-full animate-pulse bg-[var(--panel)]" />
        )}
      </span>
      <span
        className={cn(
          "block border-t px-1 py-0.5 text-center font-mono text-[10px]",
          active
            ? "border-[var(--accent-2)]/30 text-[var(--accent-2)]"
            : "border-[var(--border)] text-[var(--muted)]",
        )}
      >
        {number}
      </span>
    </button>
  );
}

export function PdfSkeleton() {
  return (
    <div
      className="flex aspect-video w-full max-w-3xl animate-pulse flex-col justify-center gap-3 rounded-lg border border-[var(--border)] bg-[var(--panel)] p-6"
      role="status"
      aria-label="Loading presentation"
    >
      <div className="h-3 w-1/3 rounded bg-[var(--border-strong)]/50" />
      <div className="h-2.5 w-4/5 rounded bg-[var(--border)]" />
      <div className="h-2.5 w-3/5 rounded bg-[var(--border)]" />
      <div className="mt-4 h-24 w-full rounded bg-[var(--border)]/60" />
    </div>
  );
}

function PdfFallback() {
  return (
    <div className="overflow-hidden rounded-2xl border border-amber-400/40 bg-[var(--panel)] shadow-card">
      <div className="flex items-start gap-3 border-b border-[var(--border)] bg-amber-500/10 p-4">
        <FileWarning aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" />
        <div>
          <p className="text-sm font-bold text-amber-700 dark:text-amber-300">
            The inline viewer could not load
          </p>
          <p className="mt-1 text-sm leading-relaxed text-[var(--muted)]">
            Your browser may block the PDF worker. The document is still available below and as a
            direct download.
          </p>
        </div>
      </div>

      <iframe
        src={PDF_URL}
        title="ScrapeFlow project presentation (PDF)"
        className="h-[min(72vh,680px)] w-full bg-slate-950"
      />

      <div className="flex flex-wrap items-center gap-3 p-4">
        <a href={PDF_URL} download={PRESENTATION_FILE} className="btn-primary">
          <Download aria-hidden="true" className="h-4 w-4" />
          Download PDF
        </a>
        <a
          href={PDF_URL}
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
