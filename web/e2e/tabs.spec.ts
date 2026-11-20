import { expect, test } from "@playwright/test";
import { createTicket, openTab, waitForStatus } from "./fixtures";

test("tabs are Ask, This week, Queue in that order and Ask is open", async ({ page }) => {
  await page.goto("/");
  const names = await page.getByRole("tab").allTextContents();
  expect(names.map((n) => n.replace(/[\d\s•]+$/, "").trim())).toEqual(["Ask", "This week", "Queue"]);
  await expect(page.getByRole("tab", { name: /^Ask/ })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByText("Support Desk", { exact: true })).toBeVisible();
  await expect(page.getByText("A person approves every answer")).toBeVisible();
});

test("a tab survives a reload", async ({ page }) => {
  await page.goto("/");
  await openTab(page, "Queue");
  await expect(page).toHaveURL(/\/\?tab=queue$/);
  await page.reload();
  await expect(page.getByRole("tab", { name: /^Queue/ })).toHaveAttribute("aria-selected", "true");
});

test("typed text survives switching tabs", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Your question", { exact: true }).fill("exit load?");
  await openTab(page, "Queue");
  await openTab(page, "Ask");
  await expect(page.getByLabel("Your question", { exact: true })).toHaveValue("exit load?");
});

test("a ticket and a tab together, and a junk tab opens Ask", async ({ page, request }) => {
  const code = await createTicket(request, "What is the expense ratio of HDFC Mid Cap Fund?");
  await page.goto(`/?t=${code}&tab=queue`);
  await expect(page.getByRole("tab", { name: /^Queue/ })).toHaveAttribute("aria-selected", "true");
  await openTab(page, "Ask");
  await expect(page.getByRole("tabpanel", { name: "Ask" }).getByText(code)).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`/\?t=${code}$`));
  await page.goto("/?tab=xyz");
  await expect(page.getByRole("tab", { name: /^Ask/ })).toHaveAttribute("aria-selected", "true");
});

test("arrow keys move between tabs", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: /^Ask/ }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: /^This week/ })).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("End");
  await expect(page.getByRole("tab", { name: /^Queue/ })).toHaveAttribute("aria-selected", "true");
});

test("queue down shows no badge number", async ({ page }) => {
  await page.route("**/api/desk/queue", (r) => r.fulfill({ status: 500, json: { detail: "The queue is down." } }));
  await page.goto("/");
  await expect(page.getByRole("tab", { name: /^Queue/ })).toHaveText(/^Queue$/);
  await openTab(page, "Queue");
  await expect(page.getByRole("tabpanel", { name: "Queue" }).getByRole("alert")).toBeVisible();
});

test("badge counts waiting tickets", async ({ page, request }) => {
  const code = await createTicket(request, "What is the minimum SIP amount for HDFC Small Cap Fund?");
  await waitForStatus(request, code, "in_review");
  await page.goto("/");
  await expect(page.getByRole("tab", { name: /^Queue/ })).toHaveText(/Queue\s*[1-9]\d*/, { timeout: 15_000 });
});
