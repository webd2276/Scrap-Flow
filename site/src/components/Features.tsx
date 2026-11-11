import {
  Activity,
  CalendarClock,
  CreditCard,
  Globe2,
  MousePointerClick,
  Package,
  Users,
  Webhook,
  type LucideIcon,
} from "lucide-react";
import { FEATURES, SECTION_COPY, type FeatureIcon } from "../data/site";
import { Reveal } from "./Reveal";
import { SectionHeading, SectionShell } from "./Section";

const ICONS: Record<FeatureIcon, LucideIcon> = {
  globe: Globe2,
  browser: MousePointerClick,
  schedule: CalendarClock,
  artifacts: Package,
  webhook: Webhook,
  tenancy: Users,
  billing: CreditCard,
  observability: Activity,
};

export function Features() {
  return (
    <SectionShell id="features" className="border-y border-[var(--border)] bg-[var(--bg-soft)]/40">
      <SectionHeading
        eyebrow={SECTION_COPY.features.eyebrow}
        title={SECTION_COPY.features.title}
        lead={SECTION_COPY.features.lead}
      />

      <ul className="mt-10 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {FEATURES.map((feature, index) => {
          const Icon = ICONS[feature.icon];
          return (
            <li key={feature.title}>
              <Reveal delay={(index % 4) * 55}>
                <div className="card card-hover h-full p-5">
                  <span className="grid h-10 w-10 place-items-center rounded-xl border border-[var(--border)] bg-gradient-to-br from-indigo-500/15 to-cyan-400/15">
                    <Icon aria-hidden="true" className="h-5 w-5 text-[var(--accent)]" />
                  </span>
                  <h3 className="mt-4 text-[15px] font-bold">{feature.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-[var(--muted)]">
                    {feature.body}
                  </p>
                </div>
              </Reveal>
            </li>
          );
        })}
      </ul>
    </SectionShell>
  );
}
