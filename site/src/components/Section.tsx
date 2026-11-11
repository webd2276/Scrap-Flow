import type { ReactNode } from "react";
import { cn } from "../lib/cn";

export function SectionShell({
  id,
  children,
  className,
}: {
  id: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section id={id} className={cn("relative py-16 sm:py-20 lg:py-24", className)}>
      <div className="container-page">{children}</div>
    </section>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  lead,
  align = "left",
}: {
  eyebrow: string;
  title: string;
  lead?: string;
  align?: "left" | "center";
}) {
  return (
    <div
      className={cn(
        "max-w-3xl",
        align === "center" && "mx-auto text-center",
      )}
    >
      <p className="eyebrow">{eyebrow}</p>
      <h2 className="mt-3 text-2xl font-bold leading-tight tracking-tight sm:text-3xl lg:text-[2.35rem]">
        {title}
      </h2>
      {lead ? (
        <p className="mt-4 text-base leading-relaxed text-[var(--muted)] sm:text-lg">
          {lead}
        </p>
      ) : null}
    </div>
  );
}
