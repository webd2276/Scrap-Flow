import { ChevronDown, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { cn } from "../lib/cn";
import { InlineText } from "./InlineText";

export interface AccordionItem {
  question: string;
  answer: string;
}

interface AccordionProps {
  items: readonly AccordionItem[];
  filterable?: boolean;
  idPrefix: string;
}

export function Accordion({ items, filterable = false, idPrefix }: AccordionProps) {
  const [open, setOpen] = useState<number | null>(0);
  const [query, setQuery] = useState("");

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return items
      .map((item, index) => ({ item, index }))
      .filter(({ item }) => {
        if (!needle) {
          return true;
        }
        return `${item.question} ${item.answer}`.toLowerCase().includes(needle);
      });
  }, [items, query]);

  return (
    <div>
      {filterable ? (
        <div className="relative mb-4 max-w-md">
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--muted)]"
          />
          <label htmlFor={`${idPrefix}-filter`} className="sr-only">
            Filter troubleshooting rows
          </label>
          <input
            id={`${idPrefix}-filter`}
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Filter by symptom or fix…"
            className="w-full rounded-xl border border-[var(--border)] bg-[var(--panel)] py-2.5 pl-9 pr-3 text-sm text-[var(--text)] placeholder:text-[var(--muted)] focus-visible:outline-none"
          />
        </div>
      ) : null}

      {visible.length === 0 ? (
        <p className="rounded-xl border border-dashed border-[var(--border)] p-4 text-sm text-[var(--muted)]">
          No rows match “{query.trim()}”.
        </p>
      ) : (
        <ul className="space-y-2">
          {visible.map(({ item, index }) => {
            const expanded = open === index;
            const panelId = `${idPrefix}-panel-${index}`;
            const buttonId = `${idPrefix}-button-${index}`;
            return (
              <li
                key={item.question}
                className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--panel)]"
              >
                <h3>
                  <button
                    type="button"
                    id={buttonId}
                    aria-expanded={expanded}
                    aria-controls={panelId}
                    onClick={() => setOpen(expanded ? null : index)}
                    className="flex w-full items-start justify-between gap-4 px-4 py-3.5 text-left text-sm font-semibold text-[var(--text)] transition hover:bg-[var(--bg-soft)]"
                  >
                    <span className="prose-inline">
                      <InlineText text={item.question} />
                    </span>
                    <ChevronDown
                      aria-hidden="true"
                      className={cn(
                        "mt-0.5 h-4 w-4 shrink-0 text-[var(--muted)] transition-transform",
                        expanded && "rotate-180",
                      )}
                    />
                  </button>
                </h3>
                {expanded ? (
                  <div
                    id={panelId}
                    role="region"
                    aria-labelledby={buttonId}
                    className="border-t border-[var(--border)] px-4 py-3.5"
                  >
                    <p className="prose-inline text-sm leading-relaxed text-[var(--muted)]">
                      <InlineText text={item.answer} />
                    </p>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
