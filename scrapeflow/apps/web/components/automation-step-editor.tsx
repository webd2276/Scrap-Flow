"use client";

import type { ReactNode } from "react";

import { Button, Input, Select, Textarea } from "@/components/ui";
import {
  STEP_ACTIONS,
  actionLabel,
  newStep,
  type BuilderStep,
  type StepAction,
} from "@/lib/automation";

function SelectorByFields({
  step,
  update,
  selectorPlaceholder = ".selector",
}: {
  step: BuilderStep;
  update: (patch: Partial<BuilderStep>) => void;
  selectorPlaceholder?: string;
}): ReactNode {
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_8rem]">
      <Input
        aria-label="Selector"
        placeholder={selectorPlaceholder}
        value={step.selector}
        onChange={(event) => update({ selector: event.target.value })}
      />
      <Select
        aria-label="Selector type"
        value={step.by}
        onChange={(event) => update({ by: event.target.value as "css" | "xpath" })}
      >
        <option value="css">CSS</option>
        <option value="xpath">XPath</option>
      </Select>
    </div>
  );
}

function ActionFields({
  step,
  update,
}: {
  step: BuilderStep;
  update: (patch: Partial<BuilderStep>) => void;
}): ReactNode {
  switch (step.action) {
    case "goto":
      return (
        <Input
          aria-label="Step URL"
          type="url"
          placeholder="https://example.com/login"
          value={step.url}
          onChange={(event) => update({ url: event.target.value })}
        />
      );
    case "click":
    case "hover":
      return <SelectorByFields step={step} update={update} />;
    case "type":
      return (
        <div className="space-y-2">
          <SelectorByFields step={step} update={update} selectorPlaceholder="input[name=email]" />
          <Textarea
            aria-label="Text to type"
            rows={2}
            placeholder="hello@example.com or {{email}}"
            value={step.text}
            onChange={(event) => update({ text: event.target.value })}
          />
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-slate-300"
              checked={step.clear}
              onChange={(event) => update({ clear: event.target.checked })}
            />
            Clear the field first
          </label>
        </div>
      );
    case "press":
      return (
        <div className="space-y-2">
          <Input
            aria-label="Key"
            placeholder="Enter"
            value={step.key}
            onChange={(event) => update({ key: event.target.value })}
          />
          <SelectorByFields
            step={step}
            update={update}
            selectorPlaceholder="optional selector; empty targets the page"
          />
        </div>
      );
    case "select":
      return (
        <div className="space-y-2">
          <SelectorByFields step={step} update={update} selectorPlaceholder="select#country" />
          <Input
            aria-label="Option value"
            placeholder="value to select"
            value={step.value}
            onChange={(event) => update({ value: event.target.value })}
          />
        </div>
      );
    case "wait_for":
      return (
        <div className="space-y-2">
          <SelectorByFields step={step} update={update} />
          <Select
            aria-label="Wait state"
            value={step.state}
            onChange={(event) =>
              update({ state: event.target.value as "present" | "visible" })
            }
          >
            <option value="visible">Visible</option>
            <option value="present">Present in DOM</option>
          </Select>
        </div>
      );
    case "sleep":
      return (
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <span>Seconds</span>
          <Input
            type="number"
            min={0.1}
            max={30}
            step={0.1}
            className="w-28"
            value={step.seconds}
            onChange={(event) =>
              update({ seconds: Number(event.target.value) || 0.1 })
            }
          />
        </label>
      );
    case "scroll":
      return (
        <div className="space-y-2">
          <SelectorByFields
            step={step}
            update={update}
            selectorPlaceholder="optional element to scroll into view"
          />
          <div className="grid grid-cols-2 gap-2">
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <span>X</span>
              <Input
                type="number"
                value={step.x}
                onChange={(event) => update({ x: Number(event.target.value) || 0 })}
              />
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <span>Y</span>
              <Input
                type="number"
                value={step.y}
                onChange={(event) => update({ y: Number(event.target.value) || 0 })}
              />
            </label>
          </div>
        </div>
      );
    case "extract":
      return (
        <div className="space-y-2">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_8rem]">
            <Input
              aria-label="Result name"
              placeholder="result name (e.g. price)"
              value={step.name}
              onChange={(event) => update({ name: event.target.value })}
            />
            <Input
              aria-label="Attribute"
              placeholder="attr (optional)"
              value={step.attr}
              onChange={(event) => update({ attr: event.target.value })}
            />
          </div>
          <SelectorByFields step={step} update={update} />
          <div className="flex flex-wrap items-center gap-4 text-sm text-slate-700">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-slate-300"
                checked={step.all}
                onChange={(event) => update({ all: event.target.checked })}
              />
              All matches
            </label>
            {step.all ? (
              <label className="flex items-center gap-2">
                <span>Limit</span>
                <Input
                  type="number"
                  min={1}
                  max={200}
                  className="w-24"
                  value={step.limit}
                  onChange={(event) =>
                    update({ limit: Math.max(1, Number(event.target.value) || 1) })
                  }
                />
              </label>
            ) : null}
          </div>
        </div>
      );
    case "get_text":
      return (
        <div className="space-y-2">
          <Input
            aria-label="Result name"
            placeholder="result name"
            value={step.name}
            onChange={(event) => update({ name: event.target.value })}
          />
          <SelectorByFields step={step} update={update} />
        </div>
      );
    case "screenshot":
      return (
        <div className="space-y-2">
          <Input
            aria-label="Screenshot name"
            placeholder="artifact name (optional)"
            value={step.name}
            onChange={(event) => update({ name: event.target.value })}
          />
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-slate-300"
              checked={step.full_page}
              onChange={(event) => update({ full_page: event.target.checked })}
            />
            Full page
          </label>
        </div>
      );
    case "execute_if_present":
      return <SelectorByFields step={step} update={update} />;
    case "loop_pages":
      return (
        <div className="space-y-2">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_8rem]">
            <Input
              aria-label="Next page selector"
              placeholder="a.next"
              value={step.next_selector}
              onChange={(event) => update({ next_selector: event.target.value })}
            />
            <Select
              aria-label="Next selector type"
              value={step.by}
              onChange={(event) => update({ by: event.target.value as "css" | "xpath" })}
            >
              <option value="css">CSS</option>
              <option value="xpath">XPath</option>
            </Select>
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <span>Max pages</span>
            <Input
              type="number"
              min={2}
              max={500}
              className="w-24"
              value={step.max_pages}
              onChange={(event) =>
                update({ max_pages: Math.max(2, Number(event.target.value) || 2) })
              }
            />
          </label>
        </div>
      );
  }
}

export function StepEditor({
  step,
  depth,
  index,
  onChange,
  onRemove,
}: {
  step: BuilderStep;
  depth: number;
  index: number;
  onChange: (step: BuilderStep) => void;
  onRemove: () => void;
}): ReactNode {
  function update(patch: Partial<BuilderStep>): void {
    onChange({ ...step, ...patch });
  }

  const isContainer =
    step.action === "execute_if_present" || step.action === "loop_pages";

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            {depth > 1 ? `${depth}.${index + 1}` : index + 1}
          </span>
          <Select
            aria-label="Step action"
            className="w-56"
            value={step.action}
            onChange={(event) => {
              const action = event.target.value as StepAction;
              const next = newStep(action);
              const nextIsContainer =
                action === "execute_if_present" || action === "loop_pages";
              onChange({
                ...next,
                id: step.id,
                optional: step.optional,
                timeout_s: step.timeout_s,
                retries: step.retries,
                steps: nextIsContainer && isContainer ? step.steps : [],
              });
            }}
          >
            {STEP_ACTIONS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </Select>
          <span className="hidden text-xs text-slate-400 sm:inline">
            {actionLabel(step.action)}
          </span>
        </div>
        <Button variant="ghost" size="sm" onClick={onRemove}>
          Remove
        </Button>
      </div>

      <div className="mt-3 space-y-3">
        <ActionFields step={step} update={update} />
      </div>

      {isContainer ? (
        <div className="mt-3 space-y-2 rounded-md border border-dashed border-slate-300 bg-slate-50 p-3">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
            Nested steps
          </p>
          {step.steps.length === 0 ? (
            <p className="text-sm text-slate-500">Add at least one nested step.</p>
          ) : null}
          {step.steps.map((child, childIndex) => (
            <StepEditor
              key={child.id}
              step={child}
              depth={depth + 1}
              index={childIndex}
              onChange={(next) =>
                update({
                  steps: step.steps.map((item) => (item.id === next.id ? next : item)),
                })
              }
              onRemove={() =>
                update({ steps: step.steps.filter((item) => item.id !== child.id) })
              }
            />
          ))}
          {depth < 3 ? (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => update({ steps: [...step.steps, newStep("click")] })}
            >
              Add nested step
            </Button>
          ) : (
            <p className="text-xs text-slate-500">Maximum nesting depth reached.</p>
          )}
        </div>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-4 border-t border-slate-100 pt-3 text-xs text-slate-600">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-slate-300"
            checked={step.optional}
            onChange={(event) => update({ optional: event.target.checked })}
          />
          Optional (continue if missing)
        </label>
        <label className="flex items-center gap-2">
          <span>Timeout (s)</span>
          <Input
            type="number"
            min={0.1}
            max={60}
            step={0.1}
            className="w-24"
            value={step.timeout_s}
            onChange={(event) =>
              update({ timeout_s: Number(event.target.value) || 0.1 })
            }
          />
        </label>
        <label className="flex items-center gap-2">
          <span>Retries</span>
          <Input
            type="number"
            min={0}
            max={3}
            className="w-20"
            value={step.retries}
            onChange={(event) =>
              update({ retries: Math.max(0, Number(event.target.value) || 0) })
            }
          />
        </label>
      </div>
    </div>
  );
}
