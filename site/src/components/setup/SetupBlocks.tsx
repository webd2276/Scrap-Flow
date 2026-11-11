import { AlertTriangle, Info, OctagonAlert } from "lucide-react";
import type { CalloutTone, SetupBlock } from "../../data/setup/types";
import { cn } from "../../lib/cn";
import { Accordion } from "../Accordion";
import { Checklist } from "../Checklist";
import { CodeBlock } from "../CodeBlock";
import { InlineText } from "../InlineText";
import { Tabs } from "../Tabs";

const TONES: Record<CalloutTone, { wrap: string; title: string; icon: typeof Info }> = {
  info: {
    wrap: "border-sky-400/50 bg-sky-500/10",
    title: "text-sky-700 dark:text-sky-300",
    icon: Info,
  },
  warn: {
    wrap: "border-amber-400/50 bg-amber-500/10",
    title: "text-amber-700 dark:text-amber-300",
    icon: AlertTriangle,
  },
  danger: {
    wrap: "border-rose-400/50 bg-rose-500/10",
    title: "text-rose-700 dark:text-rose-300",
    icon: OctagonAlert,
  },
};

function Callout({
  tone,
  title,
  text,
  items,
}: {
  tone: CalloutTone;
  title: string;
  text?: string;
  items?: string[];
}) {
  const config = TONES[tone];
  const Icon = config.icon;

  return (
    <div className={cn("rounded-xl border-l-4 p-4", config.wrap)}>
      <p className={cn("flex items-center gap-2 text-sm font-bold", config.title)}>
        <Icon aria-hidden="true" className="h-4 w-4 shrink-0" />
        {title}
      </p>
      {text ? (
        <p className="prose-inline mt-2 text-sm leading-relaxed text-[var(--text)]">
          <InlineText text={text} />
        </p>
      ) : null}
      {items && items.length > 0 ? (
        <ul className="mt-2 space-y-1.5">
          {items.map((item) => (
            <li key={item} className="prose-inline text-sm leading-relaxed text-[var(--text)]">
              <InlineText text={item} />
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function BlockList({ items, ordered }: { items: string[]; ordered?: boolean }) {
  if (ordered) {
    return (
      <ol className="list-decimal space-y-2 pl-5 text-sm leading-relaxed text-[var(--muted)] marker:font-semibold marker:text-[var(--accent-2)]">
        {items.map((item) => (
          <li key={item} className="prose-inline pl-1">
            <InlineText text={item} />
          </li>
        ))}
      </ol>
    );
  }

  return (
    <ul className="space-y-2 text-sm leading-relaxed text-[var(--muted)]">
      {items.map((item) => (
        <li key={item} className="flex gap-2.5">
          <span
            aria-hidden="true"
            className="mt-[0.55rem] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--accent-2)]"
          />
          <span className="prose-inline min-w-0">
            <InlineText text={item} />
          </span>
        </li>
      ))}
    </ul>
  );
}

function BlockTable({
  head,
  rows,
  caption,
}: {
  head: string[];
  rows: string[][];
  caption?: string;
}) {
  return (
    <div>
      <div className="scroll-slim overflow-x-auto rounded-xl border border-[var(--border)]">
        <table className="w-full min-w-[560px] border-collapse text-left text-sm">
          <thead>
            <tr className="bg-[var(--bg-soft)]">
              {head.map((cell) => (
                <th
                  key={cell}
                  scope="col"
                  className="whitespace-nowrap border-b border-[var(--border)] px-3 py-2.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]"
                >
                  {cell}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.join("|")}
                className="border-b border-[var(--border)] last:border-0 even:bg-[var(--bg-soft)]/40"
              >
                {row.map((cell, index) => (
                  <td
                    key={`${index}-${cell}`}
                    className={cn(
                      "prose-inline px-3 py-2.5 align-top text-[var(--muted)]",
                      index === 0 && "font-medium text-[var(--text)]",
                    )}
                  >
                    <InlineText text={cell} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {caption ? (
        <p className="mt-2 text-xs text-[var(--muted)]">{caption}</p>
      ) : null}
    </div>
  );
}

export function SetupBlocks({ blocks }: { blocks: SetupBlock[] }) {
  return (
    <div className="space-y-4">
      {blocks.map((block, index) => (
        <BlockSwitch key={index} block={block} index={index} />
      ))}
    </div>
  );
}

function BlockSwitch({ block, index }: { block: SetupBlock; index: number }) {
  switch (block.type) {
    case "paragraph":
      return (
        <p className="prose-inline text-sm leading-relaxed text-[var(--muted)] sm:text-[15px]">
          <InlineText text={block.text} />
        </p>
      );
    case "subheading":
      return (
        <h4 className="pt-3 text-sm font-bold uppercase tracking-[0.14em] text-[var(--text)]">
          {block.text}
        </h4>
      );
    case "code":
      return (
        <CodeBlock code={block.code} language={block.language} label={block.label} />
      );
    case "list":
      return <BlockList items={block.items} ordered={block.ordered} />;
    case "table":
      return <BlockTable head={block.head} rows={block.rows} caption={block.caption} />;
    case "callout":
      return (
        <Callout
          tone={block.tone}
          title={block.title}
          text={block.text}
          items={block.items}
        />
      );
    case "tabs":
      return (
        <Tabs
          label={`Setup options ${index + 1}`}
          tabs={block.tabs.map((tab) => ({
            label: tab.label,
            content: <SetupBlocks blocks={tab.blocks} />,
          }))}
        />
      );
    case "accordion":
      return (
        <Accordion
          items={block.items}
          filterable={block.filterable}
          idPrefix={`setup-accordion-${index}`}
        />
      );
    case "checklist":
      return <Checklist items={block.items} />;
    default:
      return null;
  }
}
