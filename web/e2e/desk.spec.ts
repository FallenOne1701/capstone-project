import { expect, type Page, test } from "@playwright/test";
import { API, createTicket } from "./fixtures";

async function askOnPage(page: Page, text: string): Promise<string> {
  await page.goto("/");
  await page.getByLabel("Your question", { exact: true }).fill(text);
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(page).toHaveURL(/\/\?t=GRW-[A-Z0-9]{6}$/);
  return new URL(page.url()).searchParams.get("t")!;
}

test("ask, then a person approves it in the queue on the same page", async ({ page }) => {
  const code = await askOnPage(page, "What is the expense ratio of HDFC Mid Cap Fund?");
  await expect(page.getByText("Waiting for a person to approve this answer.")).toBeVisible({ timeout: 45_000 });
  const card = page.getByRole("region", { name: "Queue" }).getByRole("article", { name: code });
  await expect(card.getByText("review: pass")).toBeVisible({ timeout: 15_000 });
  await card.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByRole("region", { name: "Answer" })).toContainText("Last checked", { timeout: 15_000 });
});

test("reject closes the ticket and Ask again brings the question back", async ({ page }) => {
  const text = "What is the exit load of HDFC Small Cap Fund?";
  const code = await askOnPage(page, text);
  const card = page.getByRole("region", { name: "Queue" }).getByRole("article", { name: code });
  await card.getByRole("button", { name: "Reject" }).click({ timeout: 45_000 });
  await expect(page.getByText("We couldn't answer this one.")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "Ask again" }).click();
  await expect(page.getByLabel("Your question", { exact: true })).toHaveValue(text);
  await expect(page).toHaveURL(/\/$/);
});

test("a draft the reviewer blocks cannot be approved", async ({ page, request }) => {
  const code = await createTicket(request, "What is the expense ratio of HDFC Large Cap Fund?");
  let draftId: number | undefined;
  await expect.poll(async () => {
    const items = (await (await request.get(`${API}/api/desk/queue`)).json()) as { code: string; draft: { id: number } | null }[];
    draftId = items.find((i) => i.code === code)?.draft?.id;
    return draftId !== undefined;
  }, { timeout: 45_000 }).toBe(true);
  // an edit the reviewer must block: advice and a return promise, no source
  const r = await request.post(`${API}/api/desk/drafts/${draftId}/edit`,
    { data: { reply: "You should buy this fund now, it will give you 25% returns every year." } });
  expect(r.ok()).toBeTruthy();
  expect((await r.json()).review_status).toBe("blocked");
  await page.goto("/");
  const card = page.getByRole("region", { name: "Queue" }).getByRole("article", { name: code });
  await expect(card.getByText("review: blocked")).toBeVisible();
  await expect(card.getByRole("button", { name: "Approve" })).toBeDisabled();
  await expect(card.getByText("Edit it first — the reviewer blocked this draft")).toBeVisible();
});

test("weekly approvals say exactly where they write, and fail safely without Google", async ({ page }) => {
  await page.goto("/");
  const week = page.getByRole("region", { name: "Weekly pulse" });
  const doc = week.getByRole("article").filter({ hasText: "Append to the weekly pulse Google Doc" });
  await expect(doc).toBeVisible();
  await expect(week.getByText(/Gmail draft to the product team \(.*\), not sent/)).toBeVisible();
  page.once("dialog", (d) => d.accept());
  await doc.getByRole("button", { name: "Approve" }).click();
  await expect(doc.getByText("failed", { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(doc.getByText(/PULSE_DOC_ID was not set/)).toBeVisible();
  await expect(doc.getByRole("button", { name: "Retry" })).toBeVisible();
});

test("Edit opens with the draft that arrived after the card first showed", async ({ page }) => {
  // the first queue answers show the ticket without its draft yet, as when the desk is still working
  let target: string | null = null;
  let held = 2;
  await page.route("**/api/desk/queue", async (route) => {
    const res = await route.fetch();
    const items = (await res.json()) as { code: string; status: string; draft: unknown; action: unknown }[];
    const i = items.findIndex((x) => x.code === target);
    if (i >= 0 && held > 0) {
      held -= 1;
      items[i] = { ...items[i], status: "received", draft: null, action: null };
    }
    await route.fulfill({ response: res, json: items });
  });
  const code = await askOnPage(page, "What is the minimum SIP of HDFC Flexi Cap Fund?");
  target = code;
  const card = page.getByRole("region", { name: "Queue" }).getByRole("article", { name: code });
  await expect(card.getByText("Waiting for the desk…")).toBeVisible({ timeout: 15_000 });
  await expect(card.getByText(/review: /)).toBeVisible({ timeout: 45_000 });
  const shown = (await card.locator("p.whitespace-pre-line").first().textContent())!.trim();
  await card.getByRole("button", { name: "Edit" }).click();
  await expect(card.getByLabel("Edit reply")).toHaveValue(shown);
  expect(shown.length).toBeGreaterThan(10);
});
