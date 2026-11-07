import { newClientId } from "./ids";

export type StepAction =
  | "goto"
  | "click"
  | "type"
  | "press"
  | "select"
  | "hover"
  | "wait_for"
  | "sleep"
  | "scroll"
  | "extract"
  | "get_text"
  | "screenshot"
  | "execute_if_present"
  | "loop_pages";

export type SelectorBy = "css" | "xpath";

export interface BuilderStep {
  id: string;
  action: StepAction;
  optional: boolean;
  timeout_s: number;
  retries: number;
  url: string;
  selector: string;
  by: SelectorBy;
  text: string;
  clear: boolean;
  key: string;
  value: string;
  state: "present" | "visible";
  seconds: number;
  x: number;
  y: number;
  name: string;
  attr: string;
  all: boolean;
  limit: number;
  full_page: boolean;
  next_selector: string;
  max_pages: number;
  steps: BuilderStep[];
}

export const STEP_ACTIONS: ReadonlyArray<{
  value: StepAction;
  label: string;
  group: "navigation" | "input" | "read" | "flow";
}> = [
  { value: "goto", label: "Go to URL", group: "navigation" },
  { value: "click", label: "Click", group: "input" },
  { value: "type", label: "Type text", group: "input" },
  { value: "press", label: "Press key", group: "input" },
  { value: "select", label: "Select option", group: "input" },
  { value: "hover", label: "Hover", group: "input" },
  { value: "wait_for", label: "Wait for element", group: "flow" },
  { value: "sleep", label: "Sleep", group: "flow" },
  { value: "scroll", label: "Scroll", group: "input" },
  { value: "extract", label: "Extract", group: "read" },
  { value: "get_text", label: "Get text", group: "read" },
  { value: "screenshot", label: "Screenshot", group: "read" },
  { value: "execute_if_present", label: "If present, run steps", group: "flow" },
  { value: "loop_pages", label: "Loop pages, run steps", group: "flow" },
];

const ACTION_LABELS = new Map(STEP_ACTIONS.map((item) => [item.value, item.label]));

export function actionLabel(action: StepAction): string {
  return ACTION_LABELS.get(action) ?? action;
}

export function newStep(action: StepAction = "goto"): BuilderStep {
  return {
    id: newClientId("step"),
    action,
    optional: false,
    timeout_s: 10,
    retries: 0,
    url: action === "goto" ? "https://example.com" : "",
    selector: "",
    by: "css",
    text: "",
    clear: true,
    key: "Enter",
    value: "",
    state: "visible",
    seconds: 1,
    x: 0,
    y: 0,
    name: action === "extract" || action === "get_text" ? "field" : "",
    attr: "",
    all: false,
    limit: 1,
    full_page: false,
    next_selector: "",
    max_pages: 2,
    steps: [],
  };
}

function baseStep(step: BuilderStep): Record<string, unknown> {
  return {
    action: step.action,
    optional: step.optional,
    timeout_s: step.timeout_s,
    retries: step.retries,
  };
}

function selectorFields(step: BuilderStep): Record<string, unknown> {
  return { selector: step.selector.trim(), by: step.by };
}

export function buildStep(step: BuilderStep): Record<string, unknown> {
  const base = baseStep(step);
  switch (step.action) {
    case "goto":
      return { ...base, url: step.url.trim() };
    case "click":
    case "hover":
      return { ...base, ...selectorFields(step) };
    case "type":
      return {
        ...base,
        ...selectorFields(step),
        text: step.text,
        clear: step.clear,
      };
    case "press":
      return {
        ...base,
        key: step.key,
        ...(step.selector.trim()
          ? { selector: step.selector.trim(), by: step.by }
          : {}),
      };
    case "select":
      return { ...base, ...selectorFields(step), value: step.value };
    case "wait_for":
      return { ...base, ...selectorFields(step), state: step.state };
    case "sleep":
      return { ...base, seconds: step.seconds };
    case "scroll":
      return {
        ...base,
        ...(step.selector.trim()
          ? { selector: step.selector.trim(), by: step.by }
          : {}),
        x: step.x,
        y: step.y,
      };
    case "extract":
      return {
        ...base,
        name: step.name.trim(),
        ...selectorFields(step),
        ...(step.attr.trim() ? { attr: step.attr.trim() } : {}),
        all: step.all,
        limit: step.limit,
      };
    case "get_text":
      return { ...base, name: step.name.trim(), ...selectorFields(step) };
    case "screenshot":
      return {
        ...base,
        ...(step.name.trim() ? { name: step.name.trim() } : {}),
        full_page: step.full_page,
      };
    case "execute_if_present":
      return {
        ...base,
        ...selectorFields(step),
        steps: step.steps.map(buildStep),
      };
    case "loop_pages":
      return {
        ...base,
        next_selector: step.next_selector.trim(),
        by: step.by,
        max_pages: step.max_pages,
        steps: step.steps.map(buildStep),
      };
  }
}

export function countSteps(steps: BuilderStep[]): number {
  return steps.reduce(
    (total, step) => total + 1 + countSteps(step.steps),
    0,
  );
}

const PLACEHOLDER = /\{\{([A-Za-z_][A-Za-z0-9_]{0,63})\}\}/g;

/** Secret placeholders are only interpolated by type, select, and press. */
export function missingSecret(steps: BuilderStep[], declared: Set<string>): string | null {
  for (const step of steps) {
    const text =
      step.action === "type"
        ? step.text
        : step.action === "select"
          ? step.value
          : step.action === "press"
            ? step.key
            : "";
    for (const match of text.matchAll(PLACEHOLDER)) {
      if (!declared.has(match[1])) {
        return `Step "${actionLabel(step.action)}" references {{${match[1]}}} but no secret is declared`;
      }
    }
    const nested = missingSecret(step.steps, declared);
    if (nested) return nested;
  }
  return null;
}

const NAME = /^[A-Za-z_][A-Za-z0-9_]{0,63}$/;
const ARTIFACT_NAME = /^[A-Za-z0-9_-]{1,40}$/;

/** Client-side validation that mirrors the server union before submission. */
export function validateSteps(steps: BuilderStep[], depth = 1): string | null {
  if (steps.length === 0) return "Add at least one step";
  if (countSteps(steps) > 500) return "At most 500 steps are allowed";
  if (depth > 3) return "Steps may be nested at most 3 levels";

  for (const step of steps) {
    const label = actionLabel(step.action);
    if (step.timeout_s < 0.1 || step.timeout_s > 60) {
      return `${label}: timeout must be between 0.1 and 60 seconds`;
    }
    if (step.retries < 0 || step.retries > 3) {
      return `${label}: retries must be between 0 and 3`;
    }
    switch (step.action) {
      case "goto":
        if (!/^https?:\/\/\S+$/i.test(step.url.trim())) {
          return "Go to URL must be an absolute http(s) URL";
        }
        break;
      case "click":
      case "hover":
      case "select":
      case "wait_for":
        if (!step.selector.trim()) return `${label}: a selector is required`;
        break;
      case "type":
        if (!step.selector.trim()) return "Type text: a selector is required";
        break;
      case "press":
        if (!step.key.trim()) return "Press key: a key is required";
        break;
      case "sleep":
        if (step.seconds < 0.1 || step.seconds > 30) {
          return "Sleep must be between 0.1 and 30 seconds";
        }
        break;
      case "extract":
      case "get_text":
        if (!NAME.test(step.name.trim())) {
          return `${label}: name must match [A-Za-z_][A-Za-z0-9_]{0,63}`;
        }
        if (!step.selector.trim()) return `${label}: a selector is required`;
        break;
      case "screenshot":
        if (step.name.trim() && !ARTIFACT_NAME.test(step.name.trim())) {
          return "Screenshot: name must match [A-Za-z0-9_-]{1,40}";
        }
        break;
      case "execute_if_present":
        if (!step.selector.trim()) {
          return "If present: a selector is required";
        }
        if (step.steps.length === 0) return "If present: add at least one nested step";
        break;
      case "loop_pages":
        if (!step.next_selector.trim()) {
          return "Loop pages: a next-page selector is required";
        }
        if (step.max_pages < 2 || step.max_pages > 500) {
          return "Loop pages: max pages must be between 2 and 500";
        }
        if (step.steps.length === 0) return "Loop pages: add at least one nested step";
        break;
    }
    if (step.steps.length > 0) {
      const nested = validateSteps(step.steps, depth + 1);
      if (nested) return nested;
    }
  }
  return null;
}

export interface AutomationPayloadInput {
  url: string;
  steps: BuilderStep[];
  secrets: Record<string, string>;
  selectors: Record<string, unknown>;
  extract: Record<string, unknown>;
  screenshot: boolean;
  includeHtml: boolean;
  proxyCountry: string;
  timeout: string;
  webhookUrl: string;
  headers: Record<string, string>;
}

export function buildAutomationPayload(
  input: AutomationPayloadInput,
): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    url: input.url.trim(),
    steps: input.steps.map(buildStep),
    secrets: input.secrets,
    selectors: input.selectors,
    extract: input.extract,
    screenshot: input.screenshot,
    include_html: input.includeHtml,
    headers: input.headers,
  };
  if (input.proxyCountry.trim()) {
    payload.proxy_country = input.proxyCountry.trim().toUpperCase();
  }
  if (input.timeout.trim()) payload.timeout_seconds = Number(input.timeout);
  if (input.webhookUrl.trim()) payload.webhook_url = input.webhookUrl.trim();
  return payload;
}
