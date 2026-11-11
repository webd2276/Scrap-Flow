import { useId, useState } from "react";
import { InlineText } from "./InlineText";

/** Interactive pre-publish checklist. State is intentionally memory-only. */
export function Checklist({ items }: { items: readonly string[] }) {
  const baseId = useId();
  const [checked, setChecked] = useState<ReadonlySet<number>>(new Set());

  function toggle(index: number) {
    setChecked((current) => {
      const next = new Set(current);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  }

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--panel)] p-4 sm:p-5">
      <ul className="space-y-3">
        {items.map((item, index) => {
          const id = `${baseId}-${index}`;
          const isChecked = checked.has(index);
          return (
            <li key={item}>
              <label
                htmlFor={id}
                className="flex cursor-pointer items-start gap-3 text-sm leading-relaxed"
              >
                <input
                  id={id}
                  type="checkbox"
                  checked={isChecked}
                  onChange={() => toggle(index)}
                  className="mt-0.5 h-4 w-4 shrink-0 cursor-pointer accent-[var(--accent)]"
                />
                <span
                  className={
                    isChecked
                      ? "text-[var(--muted)] line-through decoration-[var(--border-strong)]"
                      : "text-[var(--text)]"
                  }
                >
                  <span className="prose-inline">
                    <InlineText text={item} />
                  </span>
                </span>
              </label>
            </li>
          );
        })}
      </ul>
      <p className="mt-4 border-t border-[var(--border)] pt-3 text-xs text-[var(--muted)]">
        {checked.size} of {items.length} complete · state is not saved
      </p>
    </div>
  );
}
