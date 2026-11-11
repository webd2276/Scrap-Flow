import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { SECTION_COPY, VERIFIED } from "../data/site";
import { Reveal } from "./Reveal";
import { SectionHeading, SectionShell } from "./Section";

export function VerifiedScope() {
  return (
    <SectionShell id="verified" className="border-y border-[var(--border)] bg-[var(--bg-soft)]/40">
      <SectionHeading
        eyebrow={SECTION_COPY.verified.eyebrow}
        title={SECTION_COPY.verified.title}
        lead={SECTION_COPY.verified.lead}
      />

      <div className="mt-10 grid gap-4 lg:grid-cols-2">
        <Reveal>
          <div className="card h-full border-emerald-400/25 p-5 sm:p-6">
            <div className="flex items-center gap-2">
              <CheckCircle2 aria-hidden="true" className="h-5 w-5 text-emerald-400" />
              <h3 className="text-lg font-bold">Verified</h3>
              <span className="ml-auto font-mono text-[11px] text-emerald-400">
                {VERIFIED.verified.length} items
              </span>
            </div>
            <ul className="mt-4 space-y-2.5">
              {VERIFIED.verified.map((item) => (
                <li key={item} className="flex gap-2.5 text-sm leading-relaxed">
                  <CheckCircle2
                    aria-hidden="true"
                    className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400"
                  />
                  <span className="text-[var(--muted)]">{item}</span>
                </li>
              ))}
            </ul>
          </div>
        </Reveal>

        <Reveal delay={80}>
          <div className="card h-full border-amber-400/25 p-5 sm:p-6">
            <div className="flex items-center gap-2">
              <AlertTriangle aria-hidden="true" className="h-5 w-5 text-amber-400" />
              <h3 className="text-lg font-bold">Not verified</h3>
              <span className="ml-auto font-mono text-[11px] text-amber-400">
                {VERIFIED.unverified.length} items
              </span>
            </div>
            <ul className="mt-4 space-y-2.5">
              {VERIFIED.unverified.map((item) => (
                <li key={item} className="flex gap-2.5 text-sm leading-relaxed">
                  <AlertTriangle
                    aria-hidden="true"
                    className="mt-0.5 h-4 w-4 shrink-0 text-amber-400"
                  />
                  <span className="text-[var(--muted)]">{item}</span>
                </li>
              ))}
            </ul>
            <p className="mt-4 border-t border-[var(--border)] pt-3 text-xs leading-relaxed text-[var(--muted)]">
              Unverified means the code path exists but needs a real external service or a
              different operating system. It is not a claim that it works.
            </p>
          </div>
        </Reveal>
      </div>
    </SectionShell>
  );
}
