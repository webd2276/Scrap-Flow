import { Info } from "lucide-react";
import { SETUP_INTRO, SETUP_SUBSECTIONS } from "../data/setup";
import { SECTION_COPY } from "../data/site";
import { useActiveSection } from "../lib/useActiveSection";
import { InlineText } from "./InlineText";
import { SectionHeading, SectionShell } from "./Section";
import { SetupSectionView } from "./setup/SetupSectionView";
import { SetupSidebar } from "./setup/SetupSidebar";

const SUBSECTION_IDS = SETUP_SUBSECTIONS.map((section) => section.id);

export function SetupGuide() {
  const active = useActiveSection(SUBSECTION_IDS, SUBSECTION_IDS[0] ?? "prerequisites");

  return (
    <SectionShell id="setup" className="border-y border-[var(--border)] bg-[var(--bg-soft)]/40">
      <SectionHeading
        eyebrow={SECTION_COPY.setup.eyebrow}
        title={SECTION_COPY.setup.title}
        lead={SECTION_COPY.setup.lead}
      />

      <div className="mt-8 flex items-start gap-3 rounded-xl border border-[var(--border)] bg-[var(--panel)] p-4">
        <Info aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-[var(--accent-2)]" />
        <p className="prose-inline text-sm leading-relaxed text-[var(--muted)]">
          <InlineText text={SETUP_INTRO} />
        </p>
      </div>

      <div className="mt-10 lg:grid lg:grid-cols-[236px_minmax(0,1fr)] lg:gap-12">
        <SetupSidebar sections={SETUP_SUBSECTIONS} active={active} />
        <div className="min-w-0 space-y-14">
          {SETUP_SUBSECTIONS.map((section) => (
            <SetupSectionView key={section.id} section={section} />
          ))}
        </div>
      </div>
    </SectionShell>
  );
}
