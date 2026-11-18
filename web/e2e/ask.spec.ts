import { expect, test } from "@playwright/test";

test("typed question becomes a ticket", async ({ page }) => {
  await page.goto("/ask");
  await page.getByLabel("Your question").fill("What is the exit load of HDFC Mid Cap Fund?");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("Fee question · HDFC Mid Cap")).toBeVisible();
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(page).toHaveURL(/\/t\/GRW-[A-Z0-9]{6}$/);
});

test("personal details are hidden before sending", async ({ page }) => {
  await page.goto("/ask");
  await page.getByLabel("Your question").fill("my pan is ABCDE1234F, what is the exit load of HDFC Mid Cap?");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("[PAN]")).toBeVisible();
  await expect(page.getByText("ABCDE1234F")).toHaveCount(0);
});

test("two funds get one clarifying question", async ({ page }) => {
  await page.goto("/ask");
  await page.getByLabel("Your question").fill("exit load of HDFC mid cap and small cap");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText(/^HDFC (Mid|Small) Cap or HDFC (Small|Mid) Cap\?$/).first()).toBeVisible();
  const send = page.getByRole("button", { name: "Send question" });
  await expect(send).toBeDisabled();
  await page.getByRole("button", { name: "HDFC Mid Cap", exact: true }).click();
  await expect(send).toBeEnabled();
});

test("advice question shows the scope notice at once", async ({ page }) => {
  await page.goto("/ask");
  await page.getByLabel("Your question").fill("Should I buy HDFC Small Cap Fund?");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("We share facts only and can't advise on buying, selling or returns")).toBeVisible();
});
