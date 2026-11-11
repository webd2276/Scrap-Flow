import { ArrowDown, Layers } from "lucide-react";
import { LAYERS, LIFECYCLE } from "../data/architecture";
import { SECTION_COPY } from "../data/site";
import { cn } from "../lib/cn";
import { Reveal } from "./Reveal";
import { SectionHeading, SectionShell } from "./Section";

export function Architecture() {
  return (
    <SectionShell id="architecture">
      <SectionHeading
        eyebrow={SECTION_COPY.architecture.eyebrow}
        title={SECTION_COPY.architecture.title}
        lead={SECTION_COPY.architecture.lead}
      />

      <div className="mt-10 grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.95fr)] lg:gap-12">
        <div>
          <p className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">
            <Layers aria-hidden="true" className="h-4 w-4 text-[var(--accent-2)]" />
            Topology
          </p>

          <ol className="space-y-2">
            {LAYERS.map((layer, index) => (
              <li key={layer.id}>
                <Reveal delay={index * 55}>
                  <div className="card relative overflow-hidden p-4 sm:p-5">
                    <span
                      aria-hidden="true"
                      className={cn(
                        "absolute inset-y-0 left-0 w-1 bg-gradient-to-b",
                        layer.accent,
                      )}
                    />
                    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 pl-1">
                      <div className="flex items-baseline gap-2">
                        <span className="font-mono text-[11px] text-[var(--accent-2)]">
                          {String(index + 1).padStart(2, "0")}
                        </span>
                        <h3 className="text-sm font-bold uppercase tracking-[0.12em]">
                          {layer.label}
                        </h3>
                      </div>
                      <p className="text-xs text-[var(--muted)]">{layer.title}</p>
                    </div>
                    <ul className="mt-3 flex flex-wrap gap-2 pl-1">
                      {layer.items.map((item) => (
                        <li key={item} className="chip !bg-[var(--bg-soft)] font-mono text-[11px]">
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>
                </Reveal>
                {index < LAYERS.length - 1 ? (
                  <div aria-hidden="true" className="flex justify-center py-1.5">
                    <ArrowDown className="h-4 w-4 text-[var(--border-strong)]" />
                  </div>
                ) : null}
              </li>
            ))}
          </ol>
        </div>

        <div>
          <p className="mb-4 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--muted)]">
            Request lifecycle
          </p>
          <ol className="space-y-2">
            {LIFECYCLE.map((step, index) => (
              <li key={step.title}>
                <Reveal delay={index * 40}>
                  <div className="flex gap-3 rounded-xl border border-[var(--border)] bg-[var(--panel)] p-3.5">
                    <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-indigo-500/20 to-cyan-400/20 font-mono text-[11px] font-bold text-[var(--accent)]">
                      {index + 1}
                    </span>
                    <div className="min-w-0">
                      <h3 className="text-sm font-semibold">{step.title}</h3>
                      <p className="mt-0.5 text-[13px] leading-relaxed text-[var(--muted)]">
                        {step.body}
                      </p>
                    </div>
                  </div>
                </Reveal>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </SectionShell>
  );
}
