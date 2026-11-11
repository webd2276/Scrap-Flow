import {
  Cookie,
  Fingerprint,
  Gauge,
  KeyRound,
  Lock,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { SECURITY, SECTION_COPY, STRIX_NOTE, type SecurityCard } from "../data/site";
import { Reveal } from "./Reveal";
import { SectionHeading, SectionShell } from "./Section";

const ICONS: Record<SecurityCard["icon"], LucideIcon> = {
  shield: ShieldCheck,
  key: KeyRound,
  fingerprint: Fingerprint,
  lock: Lock,
  gauge: Gauge,
  cookie: Cookie,
};

export function Security() {
  return (
    <SectionShell id="security">
      <SectionHeading
        eyebrow={SECTION_COPY.security.eyebrow}
        title={SECTION_COPY.security.title}
        lead={SECTION_COPY.security.lead}
      />

      <ul className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {SECURITY.map((card, index) => {
          const Icon = ICONS[card.icon];
          return (
            <li key={card.title}>
              <Reveal delay={(index % 3) * 55}>
                <div className="card card-hover h-full p-5">
                  <span className="grid h-10 w-10 place-items-center rounded-xl border border-emerald-400/20 bg-emerald-500/10">
                    <Icon aria-hidden="true" className="h-5 w-5 text-emerald-400" />
                  </span>
                  <h3 className="mt-4 text-[15px] font-bold">{card.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-[var(--muted)]">{card.body}</p>
                </div>
              </Reveal>
            </li>
          );
        })}
      </ul>

      <Reveal delay={120}>
        <div className="mt-6 rounded-xl border border-amber-400/40 bg-amber-500/10 p-4">
          <p className="text-sm font-bold text-amber-700 dark:text-amber-300">
            Strix AI pentesting — advisory only
          </p>
          <p className="mt-1.5 text-sm leading-relaxed text-[var(--text)]">{STRIX_NOTE}</p>
        </div>
      </Reveal>
    </SectionShell>
  );
}
