import { expect, test } from "@playwright/test";
import { createTicket, waitForStatus } from "./fixtures";

test("a ticket link shows the checked answer and how it was checked", async ({ page, request }) => {
  const code = await createTicket(request, "What is the expense ratio of HDFC Small Cap Fund?");
  await waitForStatus(request, code, "answered");
  await page.goto(`/t/${code}`);                       // old links still work
  await expect(page).toHaveURL(new RegExp(`/\\?t=${code}$`));
  await expect(page.getByRole("region", { name: "Answer" })).toContainText("Last checked");
  await page.getByText("How this was checked").click();
  await expect(page.getByText("Review: passed")).toBeVisible();
  await expect(page.locator("details").getByRole("link", { name: /groww\.in\/mutual-funds/ })).toBeVisible();
});

test("unknown ticket says so", async ({ page }) => {
  await page.goto("/?t=GRW-ZZZZZZ");
  await expect(page.getByText("We couldn't find that ticket.")).toBeVisible();
});

test("old /ask link opens the main page", async ({ page }) => {
  await page.goto("/ask");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByLabel("Your question", { exact: true })).toBeVisible();
});
