"use client";

import type { ReactNode } from "react";

import { Button, Input, Select } from "@/components/ui";
import { newClientId } from "@/lib/ids";

export interface SelectorRow {
  id: string;
  name: string;
  mode: "css" | "xpath";
  value: string;
  attr: string;
  all: boolean;
  limit: number;
}

export function newSelectorRow(): SelectorRow {
  return {
    id: newClientId("selector"),
    name: "",
    mode: "css",
    value: "",
    attr: "",
    all: false,
    limit: 1,
  };
}

export function rowsToSelectors(rows: SelectorRow[]): Record<string, unknown> {
  const selectors: Record<string, unknown> = {};
  for (const row of rows) {
    const name = row.name.trim();
    const value = row.value.trim();
    if (!name || !value) continue;
    selectors[name] = {
      [row.mode]: value,
      ...(row.attr.trim() ? { attr: row.attr.trim() } : {}),
      all: row.all,
      limit: row.all ? row.limit : 1,
    };
  }
  return selectors;
}

export function SelectorEditor({
  rows,
  onChange,
  addLabel = "Add selector",
}: {
  rows: SelectorRow[];
  onChange: (rows: SelectorRow[]) => void;
  addLabel?: string;
}): ReactNode {
  function update(id: string, patch: Partial<SelectorRow>): void {
    onChange(rows.map((row) => (row.id === id ? { ...row, ...patch } : row)));
  }

  return (
    <div className="space-y-3">
      {rows.length === 0 ? (
        <p className="text-sm text-slate-500">
          No selectors. Add one to name a field in the result.
        </p>
      ) : null}
      {rows.map((row, index) => (
        <div key={row.id} className="rounded-lg border border-slate-200 p-3">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <Input
              aria-label={`Selector ${index + 1} result name`}
              placeholder="result name (e.g. price)"
              value={row.name}
              onChange={(event) => update(row.id, { name: event.target.value })}
            />
            <Select
              aria-label={`Selector ${index + 1} query type`}
              value={row.mode}
              onChange={(event) =>
                update(row.id, { mode: event.target.value as "css" | "xpath" })
              }
            >
              <option value="css">CSS</option>
              <option value="xpath">XPath</option>
            </Select>
          </div>
          <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_10rem_auto]">
            <Input
              aria-label={`Selector ${index + 1} expression`}
              placeholder={row.mode === "css" ? ".price" : "//span[@class='price']"}
              value={row.value}
              onChange={(event) => update(row.id, { value: event.target.value })}
            />
            <Input
              aria-label={`Selector ${index + 1} attribute`}
              placeholder="attribute (optional)"
              value={row.attr}
              onChange={(event) => update(row.id, { attr: event.target.value })}
            />
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onChange(rows.filter((item) => item.id !== row.id))}
            >
              Remove
            </Button>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-4 text-sm text-slate-700">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-slate-300"
                checked={row.all}
                onChange={(event) => update(row.id, { all: event.target.checked })}
              />
              Return all matches
            </label>
            {row.all ? (
              <label className="flex items-center gap-2">
                <span>Limit</span>
                <Input
                  type="number"
                  min={1}
                  max={200}
                  className="w-24"
                  value={row.limit}
                  onChange={(event) =>
                    update(row.id, {
                      limit: Math.min(200, Math.max(1, Number(event.target.value) || 1)),
                    })
                  }
                />
              </label>
            ) : null}
          </div>
        </div>
      ))}
      <Button
        variant="secondary"
        size="sm"
        onClick={() => onChange([...rows, newSelectorRow()])}
      >
        {addLabel}
      </Button>
    </div>
  );
}
