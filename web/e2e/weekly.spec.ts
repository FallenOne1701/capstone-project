import { expect, test } from "@playwright/test";
import { openTab } from "./fixtures";

test("weekly tab shows the seeded pulse", async ({ page }) => {
  await page.goto("/");
  await openTab(page, "This week");
  const week = page.getByRole("tabpanel", { name: "This week" });
  await expect(week.getByRole("heading", { name: /week ending/ })).toBeVisible();
  await expect(week.getByRole("list", { name: "Top themes" }).getByRole("listitem").first()).toBeVisible();
  await expect(week.getByRole("list", { name: "What users said" }).getByRole("listitem").first()).toBeVisible();
  await expect(week.getByRole("heading", { name: "Asked repeatedly" })).toBeVisible();
  await expect(week.getByRole("link").first()).toHaveAttribute("href", /^https:\/\//);
  await expect(week.getByText(/Google Doc: .+ · Gmail draft: .+/)).toBeVisible();
  // Run weekly now sits above the pulse
  const run = await week.getByRole("button", { name: "Run weekly now" }).boundingBox();
  const themes = await week.getByRole("list", { name: "Top themes" }).boundingBox();
  expect(run!.y).toBeLessThan(themes!.y);
});

test("explainers and sources start open", async ({ page }) => {
  await page.goto("/?tab=week");
  const week = page.getByRole("tabpanel", { name: "This week" });
  const explainers = week.locator("details", { has: page.locator("summary", { hasText: "Fee explainers" }) });
  const sources = week.locator("details", { has: page.locator("summary", { hasText: "Sources" }) });
  await expect(explainers).toHaveAttribute("open", "");
  await expect(sources).toHaveAttribute("open", "");
  await expect(sources.getByRole("link").first()).toBeVisible();
});

test("the exact text to be written shows without a click", async ({ page }) => {
  await page.goto("/?tab=week");
  const doc = page.getByRole("tabpanel", { name: "This week" }).getByRole("article").filter({ hasText: "Append to the weekly pulse Google Doc" });
  await expect(doc.getByLabel("Exactly what will be written")).toBeVisible();
});

test("no pulse yet", async ({ page }) => {
  await page.route("**/api/weekly/summary", (route) => route.fulfill({ status: 404, json: { detail: "no weekly pulse yet" } }));
  await page.goto("/?tab=week");
  await expect(page.getByText("The first weekly pulse hasn't run yet.")).toBeVisible();
});
