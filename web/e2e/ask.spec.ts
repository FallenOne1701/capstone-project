import { expect, test } from "@playwright/test";
import { approveTicket } from "./fixtures";

test("typed question is answered on the same page once a person approves", async ({ page, request }) => {
  await page.goto("/");
  await page.getByLabel("Your question", { exact: true }).fill("What is the exit load of HDFC Mid Cap Fund?");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("Fee question · HDFC Mid Cap")).toBeVisible();
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(page).toHaveURL(/\/\?t=GRW-[A-Z0-9]{6}$/);
  const code = new URL(page.url()).searchParams.get("t")!;
  await approveTicket(request, code);
  await expect(page.getByRole("region", { name: "Answer" })).toContainText("Last checked", { timeout: 45_000 });
  await expect(page.getByRole("button", { name: "Ask another question" })).toBeVisible();
});

test("rate limit message keeps typing available", async ({ page }) => {
  await page.route("**/api/ask/preview", (route) =>
    route.fulfill({ status: 429, json: { detail: "You've asked a lot of questions quickly — please wait a few minutes." } }));
  await page.goto("/");
  await page.getByLabel("Your question", { exact: true }).fill("What is the exit load of HDFC Mid Cap Fund?");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("You've asked a lot of questions quickly — please wait a few minutes.")).toBeVisible();
  await expect(page.getByLabel("Your question", { exact: true })).toBeEditable();
});

test("the console is gone", async ({ page }) => {
  const r = await page.goto("/console");
  expect(r?.status()).toBe(404);
});

test("personal details are hidden before sending", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Your question", { exact: true }).fill("my pan is ABCDE1234F, what is the exit load of HDFC Mid Cap?");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("[PAN]")).toBeVisible();
  await expect(page.getByText("ABCDE1234F")).toHaveCount(0);
});

test("two funds get one clarifying question", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Your question", { exact: true }).fill("exit load of HDFC mid cap and small cap");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText(/^HDFC (Mid|Small) Cap or HDFC (Small|Mid) Cap\?$/).first()).toBeVisible();
  const send = page.getByRole("button", { name: "Send question" });
  await expect(send).toBeDisabled();
  await page.getByRole("button", { name: "HDFC Mid Cap", exact: true }).click();
  await expect(send).toBeEnabled();
});

test("advice question shows the scope notice at once", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Your question", { exact: true }).fill("Should I buy HDFC Small Cap Fund?");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("We share facts only and can't advise on buying, selling or returns")).toBeVisible();
});

const CANNED = {
  redacted_text: "what is the exit load of HDFC mid cap", pii_types: [], intent: "fee_question",
  scheme_ids: ["hdfc-mid-cap-fund-direct-growth"], language: "en", needs_clarification: false, options: [],
  scheme_names: ["HDFC Mid Cap"],
};

test("voice question reaches confirm", async ({ page }) => {
  let uploads = 0;
  await page.route("**/api/voice/transcribe", async (route) => {
    uploads += 1;
    await route.fulfill({ json: CANNED });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Speak your question" }).click();
  await expect(page.getByText(/0:0\d \/ 1:00/)).toBeVisible();
  await page.waitForTimeout(1500);
  await page.getByRole("button", { name: "Stop recording" }).click();
  await expect(page.getByRole("tabpanel", { name: "Ask" }).getByText("what is the exit load of HDFC mid cap")).toBeVisible();
  await expect(page.getByText("Fee question · HDFC Mid Cap")).toBeVisible();
  await expect(page.getByRole("button", { name: "Re-record" })).toBeVisible();
  expect(uploads).toBe(1);
});

test("a too-short recording is never uploaded", async ({ page }) => {
  let uploads = 0;
  await page.route("**/api/voice/transcribe", async (route) => {
    uploads += 1;
    await route.fulfill({ json: CANNED });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Speak your question" }).click();
  await page.getByRole("button", { name: "Stop recording" }).click();
  await expect(page.getByText("Couldn't hear that — try again or type")).toBeVisible();
  expect(uploads).toBe(0);
});

test("voice service down falls back to typing", async ({ page }) => {
  await page.route("**/api/voice/transcribe", (route) =>
    route.fulfill({ status: 503, json: { detail: "Voice is unavailable right now — please type your question." } }));
  await page.goto("/");
  await page.getByRole("button", { name: "Speak your question" }).click();
  await page.waitForTimeout(1300);
  await page.getByRole("button", { name: "Stop recording" }).click();
  await expect(page.getByText("Voice is unavailable right now — please type your question.")).toBeVisible();
  await expect(page.getByLabel("Your question", { exact: true })).toBeEditable();
});
