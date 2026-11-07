import { describe, expect, it } from "vitest";

import {
  buildAutomationPayload,
  buildStep,
  countSteps,
  missingSecret,
  newStep,
  validateSteps,
} from "../lib/automation";

describe("newStep", () => {
  it("provides defaults for each action", () => {
    const goto = newStep("goto");
    expect(goto.action).toBe("goto");
    expect(goto.url).toBe("https://example.com");
    expect(goto.by).toBe("css");
    expect(goto.steps).toEqual([]);

    const extract = newStep("extract");
    expect(extract.name).toBe("field");
    expect(extract.limit).toBe(1);
  });

  it("creates unique ids", () => {
    expect(newStep().id).not.toBe(newStep().id);
  });
});

describe("buildStep", () => {
  it("emits only the fields for the selected action", () => {
    const goto = buildStep({ ...newStep("goto"), url: " https://example.com/a " });
    expect(goto).toMatchObject({
      action: "goto",
      url: "https://example.com/a",
      optional: false,
      timeout_s: 10,
      retries: 0,
    });
    expect(goto).not.toHaveProperty("selector");

    const type = buildStep({
      ...newStep("type"),
      selector: "#email",
      text: "{{email}}",
    });
    expect(type).toMatchObject({ action: "type", selector: "#email", text: "{{email}}" });
  });

  it("omits an empty press selector", () => {
    const press = buildStep({ ...newStep("press"), key: "Enter", selector: "  " });
    expect(press).not.toHaveProperty("selector");
    expect(press).toMatchObject({ action: "press", key: "Enter" });
  });

  it("builds nested container steps", () => {
    const container = {
      ...newStep("execute_if_present"),
      selector: ".modal",
      steps: [{ ...newStep("click"), selector: ".close" }],
    };
    const built = buildStep(container);
    expect(built.action).toBe("execute_if_present");
    expect(built.selector).toBe(".modal");
    expect(built.steps).toEqual([
      expect.objectContaining({ action: "click", selector: ".close" }),
    ]);
    expect(countSteps([container])).toBe(2);
  });
});

describe("validateSteps", () => {
  it("requires at least one step", () => {
    expect(validateSteps([])).toBe("Add at least one step");
  });

  it("validates goto URLs", () => {
    expect(validateSteps([{ ...newStep("goto"), url: "not-a-url" }])).toBe(
      "Go to URL must be an absolute http(s) URL",
    );
    expect(validateSteps([newStep("goto")])).toBeNull();
  });

  it("validates selectors and result names", () => {
    expect(validateSteps([{ ...newStep("click"), selector: "" }])).toBe(
      "Click: a selector is required",
    );
    expect(
      validateSteps([{ ...newStep("extract"), selector: ".price", name: "bad name" }]),
    ).toContain("name must match");
  });

  it("validates container children and depth", () => {
    expect(validateSteps([newStep("loop_pages")])).toBe(
      "Loop pages: a next-page selector is required",
    );
    const emptyContainer = { ...newStep("execute_if_present"), selector: ".modal" };
    expect(validateSteps([emptyContainer])).toBe(
      "If present: add at least one nested step",
    );

    const leaf = { ...newStep("click"), selector: ".x" };
    const level3 = { ...newStep("execute_if_present"), selector: ".a", steps: [leaf] };
    const level2 = { ...newStep("execute_if_present"), selector: ".b", steps: [level3] };
    const level1 = { ...newStep("execute_if_present"), selector: ".c", steps: [level2] };
    expect(validateSteps([level1])).toBe("Steps may be nested at most 3 levels");
  });
});

describe("missingSecret", () => {
  it("finds undeclared placeholders", () => {
    const step = { ...newStep("type"), selector: "#email", text: "{{email}}" };
    expect(missingSecret([step], new Set())).toContain("{{email}}");
    expect(missingSecret([step], new Set(["email"]))).toBeNull();
  });

  it("ignores placeholders outside interpolated fields", () => {
    const step = { ...newStep("click"), selector: "{{email}}" };
    expect(missingSecret([step], new Set())).toBeNull();
  });
});

describe("buildAutomationPayload", () => {
  it("includes optional fields only when set", () => {
    const payload = buildAutomationPayload({
      url: " https://example.com ",
      steps: [newStep("goto")],
      secrets: {},
      selectors: {},
      extract: { title: true },
      screenshot: false,
      includeHtml: false,
      proxyCountry: "",
      timeout: "",
      webhookUrl: "",
      headers: {},
    });
    expect(payload.url).toBe("https://example.com");
    expect(payload).not.toHaveProperty("proxy_country");
    expect(payload).not.toHaveProperty("timeout_seconds");
    expect(payload).not.toHaveProperty("webhook_url");
    expect(Array.isArray(payload.steps)).toBe(true);
  });

  it("normalises optional fields when set", () => {
    const payload = buildAutomationPayload({
      url: "https://example.com",
      steps: [newStep("goto")],
      secrets: { email: "a@example.com" },
      selectors: { price: { css: ".price" } },
      extract: { title: true },
      screenshot: true,
      includeHtml: true,
      proxyCountry: "de",
      timeout: "30",
      webhookUrl: "https://hooks.example.com/x",
      headers: { "Accept-Language": "en" },
    });
    expect(payload.proxy_country).toBe("DE");
    expect(payload.timeout_seconds).toBe(30);
    expect(payload.webhook_url).toBe("https://hooks.example.com/x");
    expect(payload.secrets).toEqual({ email: "a@example.com" });
  });
});
