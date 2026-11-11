import type { SetupSubsection } from "../../data/setup/types";
import { SetupBlocks } from "./SetupBlocks";

export function SetupSectionView({ section }: { section: SetupSubsection }) {
  return (
    <article id={section.id} className="scroll-mt-28">
      <div className="mb-4 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-mono text-xs font-semibold text-[var(--accent-2)]">
          {section.number}
        </span>
        <h3 className="text-xl font-bold tracking-tight sm:text-2xl">{section.title}</h3>
      </div>
      <SetupBlocks blocks={section.blocks} />
    </article>
  );
}
