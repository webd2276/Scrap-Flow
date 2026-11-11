import { ListTree } from "lucide-react";
import type { SetupSubsection } from "../../data/setup/types";
import { cn } from "../../lib/cn";

interface SidebarProps {
  sections: readonly SetupSubsection[];
  active: string;
}

export function SetupSidebar({ sections, active }: SidebarProps) {
  return (
    <>
      <details className="mb-8 rounded-xl border border-[var(--border)] bg-[var(--panel)] lg:hidden">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-semibold text-[var(--text)]">
          <ListTree aria-hidden="true" className="h-4 w-4 text-[var(--accent-2)]" />
          Jump to a setup step
          <span className="ml-auto text-xs font-normal text-[var(--muted)]">7.1 – 7.15</span>
        </summary>
        <nav aria-label="Setup steps" className="border-t border-[var(--border)] p-2">
          <ul className="space-y-0.5">
            {sections.map((section) => (
              <li key={section.id}>
                <a
                  href={`#${section.id}`}
                  className={cn(
                    "flex items-baseline gap-2 rounded-lg px-3 py-2 text-sm",
                    active === section.id
                      ? "bg-[var(--bg-soft)] font-semibold text-[var(--text)]"
                      : "text-[var(--muted)]",
                  )}
                >
                  <span className="font-mono text-[11px] text-[var(--accent-2)]">
                    {section.number}
                  </span>
                  {section.title}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </details>

      <nav aria-label="Setup steps" className="hidden lg:block">
        <div className="sticky top-24 max-h-[calc(100vh-7rem)] overflow-y-auto pr-2 scroll-slim">
          <p className="eyebrow mb-3">On this page</p>
          <ul className="space-y-0.5 border-l border-[var(--border)]">
            {sections.map((section) => (
              <li key={section.id}>
                <a
                  href={`#${section.id}`}
                  aria-current={active === section.id ? "true" : undefined}
                  className={cn(
                    "-ml-px flex items-baseline gap-2 border-l-2 py-1.5 pl-3 text-[13px] leading-snug transition",
                    active === section.id
                      ? "border-[var(--accent-2)] font-semibold text-[var(--text)]"
                      : "border-transparent text-[var(--muted)] hover:border-[var(--border-strong)] hover:text-[var(--text)]",
                  )}
                >
                  <span className="w-8 shrink-0 font-mono text-[10px] text-[var(--accent-2)]">
                    {section.number}
                  </span>
                  {section.title}
                </a>
              </li>
            ))}
          </ul>
        </div>
      </nav>
    </>
  );
}
