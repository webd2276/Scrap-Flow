import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, ImageOff, X } from "lucide-react";
import { SCREENSHOTS, SECTION_COPY, type Screenshot } from "../data/site";
import { assetUrl } from "../lib/asset";
import { Reveal } from "./Reveal";
import { SectionHeading, SectionShell } from "./Section";

export function Screenshots() {
  const [open, setOpen] = useState<number | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);

  const close = useCallback(() => setOpen(null), []);
  const move = useCallback(
    (delta: number) => {
      setOpen((current) =>
        current === null ? current : (current + delta + SCREENSHOTS.length) % SCREENSHOTS.length,
      );
    },
    [],
  );

  useEffect(() => {
    if (open === null) {
      return;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();

    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        close();
      } else if (event.key === "ArrowRight") {
        move(1);
      } else if (event.key === "ArrowLeft") {
        move(-1);
      }
    }

    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, close, move]);

  const current = open === null ? null : SCREENSHOTS[open];

  return (
    <SectionShell id="screenshots">
      <SectionHeading
        eyebrow={SECTION_COPY.screenshots.eyebrow}
        title={SECTION_COPY.screenshots.title}
        lead={SECTION_COPY.screenshots.lead}
      />

      <ul className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {SCREENSHOTS.map((shot, index) => (
          <li key={shot.slug}>
            <Reveal delay={(index % 3) * 55}>
              <ShotCard shot={shot} onOpen={() => setOpen(index)} />
            </Reveal>
          </li>
        ))}
      </ul>

      {current !== null ? (
        <div
          ref={dialogRef}
          role="dialog"
          aria-modal="true"
          aria-label={`${current.title} screenshot`}
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
          onClick={close}
        >
          <div
            className="relative w-full max-w-5xl overflow-hidden rounded-2xl border border-white/15 bg-[var(--panel-solid)] shadow-glow"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-3 border-b border-[var(--border)] px-4 py-2.5">
              <p className="text-sm font-semibold">{current.title}</p>
              <button
                ref={closeRef}
                type="button"
                onClick={close}
                className="icon-btn !h-8 !w-8"
                aria-label="Close screenshot preview"
              >
                <X aria-hidden="true" className="h-4 w-4" />
              </button>
            </div>

            <div className="bg-slate-950">
              <ShotImage
                shot={current}
                className="max-h-[70vh] w-full object-contain"
                eager
              />
            </div>

            <div className="flex items-center justify-between gap-3 px-4 py-3">
              <p className="min-w-0 text-xs text-[var(--muted)]">{current.blurb}</p>
              <div className="flex shrink-0 items-center gap-2">
                <button
                  type="button"
                  onClick={() => move(-1)}
                  className="icon-btn !h-8 !w-8"
                  aria-label="Previous screenshot"
                >
                  <ChevronLeft aria-hidden="true" className="h-4 w-4" />
                </button>
                <span className="font-mono text-[11px] text-[var(--muted)]">
                  {(open ?? 0) + 1} / {SCREENSHOTS.length}
                </span>
                <button
                  type="button"
                  onClick={() => move(1)}
                  className="icon-btn !h-8 !w-8"
                  aria-label="Next screenshot"
                >
                  <ChevronRight aria-hidden="true" className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </SectionShell>
  );
}

function ShotCard({ shot, onOpen }: { shot: Screenshot; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="group card w-full overflow-hidden text-left transition hover:-translate-y-0.5 hover:border-[var(--border-strong)] hover:shadow-glow"
      aria-label={`Open ${shot.title} screenshot`}
    >
      <div className="relative aspect-[16/10] overflow-hidden border-b border-[var(--border)] bg-[var(--bg-soft)]">
        <ShotImage
          shot={shot}
          className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.02]"
        />
      </div>
      <div className="p-4">
        <h3 className="text-sm font-bold">{shot.title}</h3>
        <p className="mt-1 text-xs leading-relaxed text-[var(--muted)]">{shot.blurb}</p>
      </div>
    </button>
  );
}

function ShotImage({
  shot,
  className,
  eager = false,
}: {
  shot: Screenshot;
  className?: string;
  eager?: boolean;
}) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <div
        className={`grid place-items-center bg-gradient-to-br from-indigo-500/15 via-sky-500/10 to-cyan-400/15 ${className ?? ""}`}
        style={{ minHeight: "12rem" }}
      >
        <div className="p-6 text-center">
          <ImageOff
            aria-hidden="true"
            className="mx-auto h-6 w-6 text-[var(--muted)]"
          />
          <p className="mt-2 text-xs font-semibold">{shot.title}</p>
          <p className="mt-1 text-[11px] text-[var(--muted)]">Screenshot not bundled</p>
        </div>
      </div>
    );
  }

  return (
    <img
      src={assetUrl(shot.file)}
      alt={`${shot.title} — ScrapeFlow dashboard`}
      loading={eager ? "eager" : "lazy"}
      decoding="async"
      onError={() => setFailed(true)}
      className={className}
    />
  );
}
