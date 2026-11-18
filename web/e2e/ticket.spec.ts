import { expect, test } from "@playwright/test";
import { createTicket } from "./fixtures";

test("status page shows the ticket's progress", async ({ page, request }) => {
  const code = await createTicket(request, "What is the expense ratio of HDFC Small Cap Fund?");
  await page.goto(`/t/${code}`);
  await expect(page.getByRole("heading", { name: code })).toBeVisible();
  await expect(page.getByRole("list", { name: "Ticket progress" })).toBeVisible();
  await expect(page.getByText(/^(received|in review)$/).first()).toBeVisible();
  await expect(page.getByText("A person is checking the answer")).toBeVisible({ timeout: 45_000 });
});

test("unknown ticket says so", async ({ page }) => {
  await page.goto("/t/GRW-ZZZZZZ");
  await expect(page.getByText("We couldn't find that ticket.")).toBeVisible();
});
