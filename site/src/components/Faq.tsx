import { FAQ, SECTION_COPY } from "../data/site";
import { Accordion } from "./Accordion";
import { SectionHeading, SectionShell } from "./Section";

export function Faq() {
  return (
    <SectionShell id="faq">
      <SectionHeading
        eyebrow={SECTION_COPY.faq.eyebrow}
        title={SECTION_COPY.faq.title}
        lead={SECTION_COPY.faq.lead}
      />
      <div className="mt-8 max-w-3xl">
        <Accordion items={FAQ} idPrefix="faq" />
      </div>
    </SectionShell>
  );
}
