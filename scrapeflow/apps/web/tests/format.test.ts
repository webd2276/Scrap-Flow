import { describe, expect, it } from "vitest";

import { isSafeHttpsUrl } from "../lib/api";
import {
  formatBytes,
  formatDuration,
  formatReset,
  isActiveStatus,
  prettyJson,
  shortId,
  statusTone,
  truncateMiddle,
} from "../lib/format";

describe("formatDuration", () => {
  it("handles missing values", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(undefined)).toBe("—");
    expect(formatDuration(Number.NaN)).toBe("—");
  });

  it("formats milliseconds, seconds, and minutes", () => {
    expect(formatDuration(0)).toBe("0 ms");
    expect(formatDuration(999)).toBe("999 ms");
    expect(formatDuration(1_500)).toBe("1.5 s");
    expect(formatDuration(15_000)).toBe("15 s");
    expect(formatDuration(65_000)).toBe("1m 5s");
  });
});

describe("formatBytes", () => {
  it("formats binary units", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(1_024)).toBe("1.0 KB");
    expect(formatBytes(1_536)).toBe("1.5 KB");
    expect(formatBytes(1_048_576)).toBe("1.0 MB");
    expect(formatBytes(10 * 1_048_576)).toBe("10 MB");
  });

  it("rejects invalid values", () => {
    expect(formatBytes(-1)).toBe("—");
    expect(formatBytes(Number.POSITIVE_INFINITY)).toBe("—");
  });
});

describe("formatReset", () => {
  it("formats the remaining period", () => {
    expect(formatReset(0)).toBe("now");
    expect(formatReset(120)).toBe("2m");
    expect(formatReset(3_661)).toBe("1h 1m");
    expect(formatReset(90_000)).toBe("1d 1h");
  });
});

describe("identifier helpers", () => {
  it("shortens long identifiers only", () => {
    expect(shortId("short")).toBe("short");
    expect(shortId("1234567890")).toBe("1234567890");
    expect(shortId("12345678901")).toBe("12345678…");
  });

  it("truncates in the middle", () => {
    expect(truncateMiddle("short", 10)).toBe("short");
    const value = truncateMiddle("https://example.com/a/very/long/path", 20);
    expect(value).toContain("…");
    expect(value.length).toBeLessThanOrEqual(20);
  });
});

describe("status helpers", () => {
  it("maps statuses to tones", () => {
    expect(statusTone("succeeded")).toContain("emerald");
    expect(statusTone("running")).toContain("sky");
    expect(statusTone("queued")).toContain("amber");
    expect(statusTone("failed")).toContain("rose");
    expect(statusTone("timed_out")).toContain("rose");
    expect(statusTone("cancelled")).toContain("slate");
    expect(statusTone("something-else")).toContain("slate");
  });

  it("recognises active statuses", () => {
    expect(isActiveStatus("queued")).toBe(true);
    expect(isActiveStatus("running")).toBe(true);
    expect(isActiveStatus("succeeded")).toBe(false);
    expect(isActiveStatus("failed")).toBe(false);
  });
});

describe("isSafeHttpsUrl", () => {
  it("accepts https and rejects script or plain-http redirects", () => {
    expect(isSafeHttpsUrl("https://checkout.stripe.com/c/pay")).toBe(true);
    expect(isSafeHttpsUrl("http://checkout.stripe.com/c/pay")).toBe(false);
    expect(isSafeHttpsUrl("javascript:alert(1)")).toBe(false);
    expect(isSafeHttpsUrl("not a url")).toBe(false);
  });

  it("enforces an optional host allowlist", () => {
    expect(
      isSafeHttpsUrl("https://checkout.stripe.com/c/pay", ["checkout.stripe.com"]),
    ).toBe(true);
    expect(
      isSafeHttpsUrl("https://evil.example/c/pay", ["checkout.stripe.com"]),
    ).toBe(false);
  });
});

describe("prettyJson", () => {
  it("pretty prints JSON", () => {
    expect(prettyJson({ a: 1 })).toBe('{\n  "a": 1\n}');
    expect(prettyJson(null)).toBe("null");
    expect(prettyJson(undefined)).toBe("null");
  });

  it("falls back for circular values", () => {
    const value: Record<string, unknown> = {};
    value.self = value;
    expect(prettyJson(value)).toBe("[object Object]");
  });
});
