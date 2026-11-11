import type { ReactNode } from "react";

/**
 * Minimal inline formatter for the setup copy: `code`, **bold** and
 * [links](https://example.com). Anything else is rendered as text, so no
 * untrusted HTML ever reaches the DOM.
 */
const TOKEN = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)\s]+\))/g;

export function InlineText({
  text,
  className,
}: {
  text: string;
  className?: string;
}) {
  const parts = text.split(TOKEN);

  return (
    <span className={className}>
      {parts.map((part, index) => {
        if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
          return (
            <strong key={index} className="font-semibold text-[var(--text)]">
              {part.slice(2, -2)}
            </strong>
          );
        }

        if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
          return <code key={index}>{part.slice(1, -1)}</code>;
        }

        const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(part);
        if (link) {
          const [, label, href] = link;
          const external = /^https?:\/\//.test(href);
          return (
            <a
              key={index}
              href={href}
              className="break-words text-[var(--accent-2)] underline decoration-dotted underline-offset-4 hover:decoration-solid"
              {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
            >
              {label}
            </a>
          );
        }

        return <FragmentText key={index} value={part} />;
      })}
    </span>
  );
}

function FragmentText({ value }: { value: string }): ReactNode {
  return <>{value}</>;
}
