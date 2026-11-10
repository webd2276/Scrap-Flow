import { describe, expect, it } from "vitest";
import { platformAreas, projectHighlights } from "../src/data/project-highlights";
import { projectResources, repositoryFileUrl } from "../src/data/resources";

describe("ScrapeFlow showcase content", () => {
  it("labels the dated local report results and keeps hosted CI unverified", () => {
    const checks = projectHighlights.find((item) => item.label === "Automated checks");
    const coverage = projectHighlights.find((item) => item.label === "Branch and line coverage");
    const hosted = projectHighlights.find((item) => item.label === "Hosted GitHub Actions run");

    expect(checks).toMatchObject({
      value: "322 passed · 3 skipped",
      context: "Local verification report, 2026-11-08",
      status: "Reported locally",
    });
    expect(coverage?.value).toBe("83.08%");
    expect(hosted).toMatchObject({ value: "Not observed", status: "Unverified" });
  });

  it("lists the documented platform components", () => {
    expect(platformAreas.map(({ technology }) => technology)).toEqual([
      "FastAPI",
      "Celery workers",
      "Selenium Grid",
      "Next.js",
    ]);
    expect(platformAreas.every(({ status }) => status === "Implemented")).toBe(true);
  });

  it("links to repository documents instead of duplicating their contents", () => {
    expect(projectResources.map(({ path }) => path)).toEqual([
      "SETUP.md",
      "docs/FINAL_REPORT.md",
      "docs/presentation/README.md",
      "docs/presentation/ScrapeFlow-Project-Presentation.pdf",
    ]);
    expect(repositoryFileUrl("docs/FINAL_REPORT.md")).toContain("github.com");
  });
});
