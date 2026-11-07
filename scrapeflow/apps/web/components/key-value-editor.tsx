"use client";

import type { ReactNode } from "react";

import { Button, Input } from "@/components/ui";
import { newClientId } from "@/lib/ids";

export interface KeyValueRow {
  id: string;
  name: string;
  value: string;
}

export function newKeyValueRow(name = "", value = ""): KeyValueRow {
  return { id: newClientId("kv"), name, value };
}

export function KeyValueEditor({
  rows,
  onChange,
  namePlaceholder = "Name",
  valuePlaceholder = "Value",
  secret = false,
  addLabel = "Add row",
  max = 20,
}: {
  rows: KeyValueRow[];
  onChange: (rows: KeyValueRow[]) => void;
  namePlaceholder?: string;
  valuePlaceholder?: string;
  secret?: boolean;
  addLabel?: string;
  max?: number;
}): ReactNode {
  function update(id: string, patch: Partial<KeyValueRow>): void {
    onChange(rows.map((row) => (row.id === id ? { ...row, ...patch } : row)));
  }

  return (
    <div className="space-y-2">
      {rows.map((row) => (
        <div
          key={row.id}
          className="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)_auto]"
        >
          <Input
            aria-label={namePlaceholder}
            placeholder={namePlaceholder}
            value={row.name}
            onChange={(event) => update(row.id, { name: event.target.value })}
          />
          <Input
            aria-label={valuePlaceholder}
            placeholder={valuePlaceholder}
            type={secret ? "password" : "text"}
            autoComplete="off"
            value={row.value}
            onChange={(event) => update(row.id, { value: event.target.value })}
          />
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onChange(rows.filter((item) => item.id !== row.id))}
          >
            Remove
          </Button>
        </div>
      ))}
      {rows.length < max ? (
        <Button
          variant="secondary"
          size="sm"
          onClick={() => onChange([...rows, newKeyValueRow()])}
        >
          {addLabel}
        </Button>
      ) : null}
    </div>
  );
}

export function rowsToRecord(rows: KeyValueRow[]): Record<string, string> {
  const record: Record<string, string> = {};
  for (const row of rows) {
    const name = row.name.trim();
    if (!name) continue;
    record[name] = row.value;
  }
  return record;
}
