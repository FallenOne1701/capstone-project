import { expect, test } from "@playwright/test";

test("weekly section shows the seeded pulse", async ({ page }) => {
  await page.goto("/");
  const week = page.getByRole("region", { name: "Weekly pulse" });
  await expect(week.getByRole("heading", { name: /week ending/ })).toBeVisible();
  await expect(week.getByRole("list", { name: "Top themes" }).getByRole("listitem").first()).toBeVisible();
  await expect(week.getByRole("list", { name: "What users said" }).getByRole("listitem").first()).toBeVisible();
  await expect(week.getByRole("link").first()).toHaveAttribute("href", /^https:\/\//);
  await expect(week.getByText(/Google Doc: .+ · Gmail draft: .+/)).toBeVisible();
});

test("no pulse yet", async ({ page }) => {
  await page.route("**/api/weekly/summary", (route) => route.fulfill({ status: 404, json: { detail: "no weekly pulse yet" } }));
  await page.goto("/");
  await expect(page.getByText("The first weekly pulse hasn't run yet.")).toBeVisible();
});
