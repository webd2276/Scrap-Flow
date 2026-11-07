import { describe, expect, it } from "vitest";

import { safeFilename } from "../lib/download";

describe("safeFilename", () => {
  it("keeps ordinary names", () => {
    expect(safeFilename("job-123.csv")).toBe("job-123.csv");
    expect(safeFilename("screenshot.png")).toBe("screenshot.png");
  });

  it("strips path separators and control characters", () => {
    expect(safeFilename("../../etc/passwd")).toBe(".._.._etc_passwd");
    expect(safeFilename("folder\\file.json")).toBe("folder_file.json");
    expect(safeFilename("bad\u0000name.txt")).toBe("badname.txt");
  });

  it("falls back for empty or traversal-only names", () => {
    expect(safeFilename("", "fallback.json")).toBe("fallback.json");
    expect(safeFilename("..", "fallback.json")).toBe("fallback.json");
    expect(safeFilename("   ", "fallback.json")).toBe("fallback.json");
  });

  it("bounds very long names", () => {
    expect(safeFilename("a".repeat(500), "fallback")).toHaveLength(128);
  });
});
