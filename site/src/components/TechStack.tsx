import { SECTION_COPY } from "../data/site";
import { STACK_TABS } from "../data/stack";
import { SectionHeading, SectionShell } from "./Section";
import { Tabs } from "./Tabs";

export function TechStack() {
  return (
    <SectionShell id="stack" className="border-y border-[var(--border)] bg-[var(--bg-soft)]/40">
      <SectionHeading
        eyebrow={SECTION_COPY.stack.eyebrow}
        title={SECTION_COPY.stack.title}
        lead={SECTION_COPY.stack.lead}
      />

      <div className="mt-8">
        <Tabs
          label="Technology stack"
          tabs={STACK_TABS.map((tab) => ({
            label: tab.label,
            content: (
              <div>
                <div className="scroll-slim overflow-x-auto rounded-xl border border-[var(--border)]">
                  <table className="w-full min-w-[720px] border-collapse text-left text-sm">
                    <thead>
                      <tr className="bg-[var(--bg-soft)]">
                        <th
                          scope="col"
                          className="border-b border-[var(--border)] px-3 py-2.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]"
                        >
                          Layer
                        </th>
                        <th
                          scope="col"
                          className="border-b border-[var(--border)] px-3 py-2.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]"
                        >
                          Technology
                        </th>
                        <th
                          scope="col"
                          className="border-b border-[var(--border)] px-3 py-2.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]"
                        >
                          Version
                        </th>
                        <th
                          scope="col"
                          className="border-b border-[var(--border)] px-3 py-2.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]"
                        >
                          Role
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {tab.rows.map((row) => (
                        <tr
                          key={`${row.layer}-${row.technology}`}
                          className="border-b border-[var(--border)] last:border-0 even:bg-[var(--bg-soft)]/40"
                        >
                          <td className="px-3 py-2.5 align-top text-[var(--muted)]">{row.layer}</td>
                          <td className="px-3 py-2.5 align-top font-semibold">{row.technology}</td>
                          <td className="whitespace-nowrap px-3 py-2.5 align-top font-mono text-xs text-[var(--accent-2)]">
                            {row.version}
                          </td>
                          <td className="px-3 py-2.5 align-top text-[var(--muted)]">{row.role}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {tab.note ? (
                  <p className="mt-3 max-w-3xl text-xs leading-relaxed text-[var(--muted)]">
                    {tab.note}
                  </p>
                ) : null}
              </div>
            ),
          }))}
        />
      </div>
    </SectionShell>
  );
}
