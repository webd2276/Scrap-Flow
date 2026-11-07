import { expect, test } from "@playwright/test";

test.describe("public pages", () => {
  test("login page renders the sign-in form", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByLabel("Password")).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Create an organisation" })).toBeVisible();
  });

  test("signup page requires terms acceptance", async ({ page }) => {
    await page.goto("/signup");
    await expect(
      page.getByRole("heading", { name: "Create your organisation" }),
    ).toBeVisible();
    await page.getByLabel("Organisation name").fill("E2E Terms Org");
    await page.getByLabel("Email").fill("terms@example.com");
    await page.getByLabel("Password").fill("correct horse battery staple");
    // Required fields are valid, so the custom terms error is reachable.
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(
      page.getByText("Accept the Terms of Service and acceptable-use policy to continue"),
    ).toBeVisible();
  });

  test("terms page documents acceptable use", async ({ page }) => {
    await page.goto("/terms");
    await expect(
      page.getByRole("heading", { name: "Terms of Service and Acceptable Use" }),
    ).toBeVisible();
    await expect(page.getByText("No evasive features")).toBeVisible();
  });

  test("anonymous dashboard visit redirects to login", async ({ page }) => {
    await page.goto("/jobs");
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  });
});

test.describe("dashboard journey", () => {
  test("signs up and drives keys, scrape, automation, schedules, and exports", async ({
    page,
  }) => {
    const stamp = Date.now();
    const email = `e2e-${stamp}@example.com`;
    const password = "correct horse battery staple";

    await page.goto("/signup");
    await page.getByLabel("Organisation name").fill(`E2E Org ${stamp}`);
    await page.getByLabel("Your name").fill("E2E User");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("checkbox").check();
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page).toHaveURL(/\/jobs$/);
    await expect(page.getByRole("heading", { name: "Jobs", exact: true })).toBeVisible();

    // API key creation shows the full secret exactly once.
    await page.goto("/keys");
    await page.getByLabel("Name").fill(`E2E key ${stamp}`);
    await page.getByRole("button", { name: "Create key" }).click();
    await expect(page.getByText("New API key")).toBeVisible();
    await expect(page.getByRole("button", { name: "Copy key" })).toBeVisible();
    await page.getByRole("button", { name: "I have stored it" }).click();

    // Submit a scrape, open its detail, and stream an export.
    await page.goto("/scrape");
    await page.getByPlaceholder("https://example.com/pricing").fill("https://example.com");
    await page.getByRole("button", { name: "Queue scrape" }).click();
    await expect(page.getByText(/Job queued/)).toBeVisible();
    await page.getByRole("link", { name: "Open job detail" }).click();
    await expect(page.getByRole("heading", { name: "Job detail" })).toBeVisible();
    const jobExport = page.waitForEvent("download");
    await page.getByRole("button", { name: "Export JSON" }).click();
    expect((await jobExport).suggestedFilename()).toMatch(/\.json$/);
    // Free plans allow one concurrent job; cancel it before queuing the next.
    page.once("dialog", (dialog) => void dialog.accept());
    await page.getByRole("button", { name: "Cancel job" }).click();
    await expect(page.getByText("cancelled", { exact: true })).toBeVisible();

    // Build a three-step browser automation and submit it.
    await page.goto("/automate");
    await page.getByRole("textbox", { name: "URL", exact: true }).fill("https://example.com");
    await page.getByRole("button", { name: "Add step" }).click();
    await page.getByRole("button", { name: "Add step" }).click();
    await page.getByLabel("Step action").nth(2).selectOption("wait_for");
    await page.getByLabel("Selector", { exact: true }).nth(0).fill("#next");
    await page.getByLabel("Selector", { exact: true }).nth(1).fill("body");
    await expect(page.getByText("3 steps")).toBeVisible();
    await page.getByRole("button", { name: "Queue automation" }).click();
    await expect(page.getByText(/Job queued/)).toBeVisible();
    await page.getByRole("link", { name: "Open job detail" }).click();
    await expect(page.getByRole("heading", { name: "Job detail" })).toBeVisible();
    page.once("dialog", (dialog) => void dialog.accept());
    await page.getByRole("button", { name: "Cancel job" }).click();
    await expect(page.getByText("cancelled", { exact: true })).toBeVisible();

    // Create a schedule and export its run history.
    await page.goto("/schedules");
    await page.getByRole("textbox", { name: "Name", exact: true }).fill(`E2E schedule ${stamp}`);
    await page.getByRole("button", { name: "Create schedule" }).click();
    await expect(page.getByText("Schedule created.")).toBeVisible();
    await expect(page.getByText(`E2E schedule ${stamp}`)).toBeVisible();
    const scheduleExport = page.waitForEvent("download");
    await page.getByRole("button", { name: "CSV" }).first().click();
    expect((await scheduleExport).suggestedFilename()).toMatch(/\.csv$/);

    await page.goto("/billing");
    await expect(page.getByRole("heading", { name: "Usage and billing" })).toBeVisible();

    // Sign out and sign back in through the public login form.
    await page.getByRole("button", { name: "Sign out" }).first().click();
    await expect(page).toHaveURL(/\/login$/);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/jobs$/);
  });
});

const email = process.env.E2E_EMAIL;
const password = process.env.E2E_PASSWORD;

test.describe("authenticated dashboard", () => {
  test.skip(
    !email || !password,
    "Set E2E_EMAIL and E2E_PASSWORD to exercise the authenticated dashboard",
  );

  test("signs in and opens every dashboard route", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill(email ?? "");
    await page.getByLabel("Password").fill(password ?? "");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/jobs$/);
    await expect(page.getByRole("heading", { name: "Jobs", exact: true })).toBeVisible();

    for (const [path, heading] of [
      ["/scrape", "New scrape"],
      ["/automate", "New automation"],
      ["/schedules", "Schedules"],
      ["/keys", "API keys"],
      ["/billing", "Usage and billing"],
    ] as const) {
      await page.goto(path);
      await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    }
  });

  test("signs out", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill(email ?? "");
    await page.getByLabel("Password").fill(password ?? "");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/jobs$/);
    await page.getByRole("button", { name: "Sign out" }).first().click();
    await expect(page).toHaveURL(/\/login$/);
  });
});
