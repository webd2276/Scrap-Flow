import { ArrowUp, Github } from "lucide-react";
import { FOOTER, REPO_NAME, REPO_URL } from "../data/site";

export function Footer() {
  function backToTop() {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: reduced ? "auto" : "smooth" });
  }

  return (
    <footer className="border-t border-[var(--border)] bg-[var(--bg-soft)]/50">
      <div className="container-page flex flex-col gap-6 py-10 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-indigo-400 to-cyan-300 font-mono text-xs font-extrabold text-slate-950">
              SF
            </span>
            <span className="text-sm font-bold">ScrapeFlow</span>
          </div>
          <p className="mt-2 text-xs text-[var(--muted)]">{FOOTER.tagline}</p>
          <p className="mt-1 text-xs text-[var(--muted)]">
            {FOOTER.note} · <span className="font-mono">{REPO_NAME}</span>
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <a
            href={REPO_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-ghost !py-2 text-xs"
          >
            <Github aria-hidden="true" className="h-4 w-4" />
            Repository
          </a>
          <button type="button" onClick={backToTop} className="btn-ghost !py-2 text-xs">
            <ArrowUp aria-hidden="true" className="h-4 w-4" />
            Back to top
          </button>
        </div>
      </div>
    </footer>
  );
}
