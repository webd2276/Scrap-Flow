"use client";

import type { ReactNode } from "react";

import { Input } from "@/components/ui";

export interface ExtractOptionsState {
  title: boolean;
  text: boolean;
  links: boolean;
  meta: boolean;
  maxTextChars: number;
  maxLinks: number;
}

export const DEFAULT_EXTRACT_OPTIONS: ExtractOptionsState = {
  title: true,
  text: true,
  links: false,
  meta: false,
  maxTextChars: 50_000,
  maxLinks: 200,
};

export function extractOptionsPayload(
  options: ExtractOptionsState,
): Record<string, unknown> {
  return {
    title: options.title,
    text: options.text,
    links: options.links,
    meta: options.meta,
    max_text_chars: options.maxTextChars,
    max_links: options.maxLinks,
  };
}

export function ExtractOptionsEditor({
  value,
  onChange,
}: {
  value: ExtractOptionsState;
  onChange: (value: ExtractOptionsState) => void;
}): ReactNode {
  const toggles: Array<{ key: keyof ExtractOptionsState; label: string }> = [
    { key: "title", label: "Page title" },
    { key: "text", label: "Visible text" },
    { key: "links", label: "Links" },
    { key: "meta", label: "Meta tags" },
  ];

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {toggles.map((item) => (
          <label
            key={item.key}
            className="flex items-center gap-2 text-sm text-slate-700"
          >
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-slate-300"
              checked={Boolean(value[item.key])}
              onChange={(event) =>
                onChange({ ...value, [item.key]: event.target.checked })
              }
            />
            {item.label}
          </label>
        ))}
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="block text-sm text-slate-700">
          <span className="mb-1 block">Max text characters</span>
          <Input
            type="number"
            min={10}
            max={500_000}
            value={value.maxTextChars}
            onChange={(event) =>
              onChange({
                ...value,
                maxTextChars: Math.min(
                  500_000,
                  Math.max(10, Number(event.target.value) || 10),
                ),
              })
            }
          />
        </label>
        <label className="block text-sm text-slate-700">
          <span className="mb-1 block">Max links</span>
          <Input
            type="number"
            min={1}
            max={1000}
            value={value.maxLinks}
            onChange={(event) =>
              onChange({
                ...value,
                maxLinks: Math.min(
                  1000,
                  Math.max(1, Number(event.target.value) || 1),
                ),
              })
            }
          />
        </label>
      </div>
    </div>
  );
}
