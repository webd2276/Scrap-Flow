import { ArrowRight, ScanSearch } from "lucide-react";
import { OVERVIEW } from "../data/site";
import { Reveal } from "./Reveal";
import { SectionHeading, SectionShell } from "./Section";

export function Overview() {
  return (
    <SectionShell id="overview">
      <SectionHeading eyebrow={OVERVIEW.eyebrow} title={OVERVIEW.heading} />

      <div className="mt-10 grid gap-4 sm:grid-cols-2">
        {OVERVIEW.cards.map((card, index) => (
          <Reveal key={card.title} delay={index * 60}>
            <div className="card card-hover h-full p-5">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[11px] font-semibold text-[var(--accent-2)]">
                  0{index + 1}
                </span>
                <h3 className="text-base font-bold">{card.title}</h3>
              </div>
              <p className="mt-2 text-sm leading-relaxed text-[var(--muted)]">{card.body}</p>
            </div>
          </Reveal>
        ))}
      </div>

      <Reveal delay={120}>
        <div className="mt-6 overflow-hidden rounded-2xl border border-indigo-400/30 bg-gradient-to-r from-indigo-500/10 via-sky-500/5 to-cyan-400/10 p-5 sm:p-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-indigo-400/30 bg-[var(--panel)]">
              <ScanSearch aria-hidden="true" className="h-5 w-5 text-indigo-300" />
            </span>
            <p className="text-sm font-semibold leading-relaxed sm:text-base">
              {OVERVIEW.solution}
            </p>
          </div>
        </div>
      </Reveal>

      <div className="mt-6 flex justify-end">
        <a
          href="#architecture"
          className="inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--accent-2)] hover:underline"
        >
          See how the pieces fit
          <ArrowRight aria-hidden="true" className="h-4 w-4" />
        </a>
      </div>
    </SectionShell>
  );
}
