import { Check, Copy, Terminal } from "lucide-react";
import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { copyText } from "../lib/clipboard";
import { cn } from "../lib/cn";
import { useInView } from "../lib/useInView";
import { ErrorBoundary } from "./ErrorBoundary";

// prism-react-renderer is not needed for first paint; only code blocks that
// approach the viewport pull it in.
const PrismHighlighter = lazy(() => import("./PrismHighlighter"));

interface CodeBlockProps {
  code: string;
  language: string;
  label?: string;
  className?: string;
}

type CopyState = "idle" | "copied" | "failed";

function PlainCode({ code }: { code: string }) {
  return (
    <pre className="scroll-slim overflow-x-auto p-4 text-[12.5px] leading-6 text-slate-300">
      {code}
    </pre>
  );
}

/** Code blocks stay dark in both themes: predictable contrast for commands. */
export function CodeBlock({ code, language, label, className }: CodeBlockProps) {
  const [state, setState] = useState<CopyState>("idle");
  const timer = useRef<number | null>(null);
  const [surfaceRef, inView] = useInView<HTMLDivElement>({
    once: true,
    rootMargin: "240px",
    threshold: 0.01,
  });

  useEffect(() => {
    return () => {
      if (timer.current !== null) {
        window.clearTimeout(timer.current);
      }
    };
  }, []);

  async function handleCopy() {
    const ok = await copyText(code);
    setState(ok ? "copied" : "failed");
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
    }
    timer.current = window.setTimeout(() => setState("idle"), 1800);
  }

  const trimmed = code.replace(/\s+$/, "");

  return (
    <div
      ref={surfaceRef}
      className={cn(
        "group overflow-hidden rounded-xl border border-white/10 bg-[var(--code-bg)] shadow-card",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-3 border-b border-white/10 bg-white/[0.04] px-3 py-2">
        <span className="inline-flex min-w-0 items-center gap-2 font-mono text-[11px] uppercase tracking-[0.14em] text-slate-300">
          <Terminal aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-cyan-300" />
          <span className="truncate">{label ?? language}</span>
        </span>
        <div className="flex shrink-0 items-center gap-2">
          <span className="hidden font-mono text-[10px] uppercase tracking-wider text-slate-500 sm:inline">
            {language}
          </span>
          <button
            type="button"
            onClick={handleCopy}
            className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-[11px] font-semibold text-slate-200 transition hover:border-cyan-300/40 hover:bg-white/10"
            aria-label={`Copy ${label ?? language} code`}
          >
            {state === "copied" ? (
              <Check aria-hidden="true" className="h-3.5 w-3.5 text-emerald-400" />
            ) : (
              <Copy aria-hidden="true" className="h-3.5 w-3.5" />
            )}
            {state === "copied" ? "Copied" : state === "failed" ? "Copy failed" : "Copy"}
          </button>
        </div>
      </div>

      {inView ? (
        <ErrorBoundary fallback={<PlainCode code={trimmed} />}>
          <Suspense fallback={<PlainCode code={trimmed} />}>
            <PrismHighlighter code={trimmed} language={language} />
          </Suspense>
        </ErrorBoundary>
      ) : (
        <PlainCode code={trimmed} />
      )}

      <span role="status" aria-live="polite" className="sr-only">
        {state === "copied" ? "Copied to clipboard" : ""}
      </span>
    </div>
  );
}

