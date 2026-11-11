import { useId, useRef, useState, type ReactNode } from "react";
import { cn } from "../lib/cn";

export interface TabItem {
  label: string;
  content: ReactNode;
}

export function Tabs({ tabs, label }: { tabs: readonly TabItem[]; label: string }) {
  const baseId = useId();
  const [active, setActive] = useState(0);
  const buttons = useRef<Array<HTMLButtonElement | null>>([]);

  function move(delta: number) {
    const next = (active + delta + tabs.length) % tabs.length;
    setActive(next);
    buttons.current[next]?.focus();
  }

  return (
    <div>
      <div
        role="tablist"
        aria-label={label}
        className="flex flex-wrap gap-2 rounded-xl border border-[var(--border)] bg-[var(--bg-soft)] p-1.5"
      >
        {tabs.map((tab, index) => {
          const selected = index === active;
          return (
            <button
              key={tab.label}
              ref={(element) => {
                buttons.current[index] = element;
              }}
              type="button"
              role="tab"
              id={`${baseId}-tab-${index}`}
              aria-selected={selected}
              aria-controls={`${baseId}-panel-${index}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => setActive(index)}
              onKeyDown={(event) => {
                if (event.key === "ArrowRight") {
                  event.preventDefault();
                  move(1);
                } else if (event.key === "ArrowLeft") {
                  event.preventDefault();
                  move(-1);
                } else if (event.key === "Home") {
                  event.preventDefault();
                  move(-active);
                } else if (event.key === "End") {
                  event.preventDefault();
                  move(tabs.length - 1 - active);
                }
              }}
              className={cn(
                "rounded-lg px-3.5 py-2 text-sm font-semibold transition",
                selected
                  ? "bg-[var(--panel-solid)] text-[var(--text)] shadow-card"
                  : "text-[var(--muted)] hover:text-[var(--text)]",
              )}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {tabs.map((tab, index) => (
        <div
          key={tab.label}
          role="tabpanel"
          id={`${baseId}-panel-${index}`}
          aria-labelledby={`${baseId}-tab-${index}`}
          hidden={index !== active}
          className="mt-4"
        >
          {tab.content}
        </div>
      ))}
    </div>
  );
}
