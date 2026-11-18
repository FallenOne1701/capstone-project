import { expect, test } from "@playwright/test";
import { createTicket, login, waitForStatus } from "./fixtures";

test("wrong password stays locked", async ({ page }) => {
  await page.goto("/console");
  await page.getByLabel("Console password").fill("not-the-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Wrong password")).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign out" })).toHaveCount(0);
});

test("approve publishes the answer", async ({ page, request }) => {
  const code = await createTicket(request, "What is the exit load of HDFC Mid Cap Fund?");
  await waitForStatus(request, code, "in_review");
  await login(page);
  const card = page.getByRole("article", { name: code });
  await expect(card).toBeVisible();
  await expect(card.getByText("Fee question")).toBeVisible();
  await card.getByRole("button", { name: "Approve" }).click();
  await expect(card.getByText("executed")).toBeVisible();

  await page.goto(`/t/${code}`);
  await expect(page.getByRole("region", { name: "Answer" })).toContainText("Last checked");
  await expect(page.getByRole("button", { name: /Listen/ })).toBeVisible();
});

test("edit re-reviews the draft before approval", async ({ page, request }) => {
  const code = await createTicket(request, "What is the minimum SIP for HDFC Small Cap Fund?");
  await waitForStatus(request, code, "in_review");
  await login(page);
  const card = page.getByRole("article", { name: code });
  await card.getByRole("button", { name: "Edit" }).click();
  const box = card.getByLabel("Edit reply");
  await box.fill("You can start a SIP in HDFC Small Cap Fund from the amount shown on the official page.");
  await card.getByRole("button", { name: "Save edit" }).click();
  await expect(card.getByText(/edited/i).first()).toBeVisible();
});
