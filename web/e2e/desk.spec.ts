import { expect, type Page, test } from "@playwright/test";
import { API, approveTicket, createTicket, openTab, rejectTicket, waitForStatus } from "./fixtures";

async function askOnPage(page: Page, text: string): Promise<string> {
  await page.goto("/");
  await page.getByLabel("Your question", { exact: true }).fill(text);
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(page).toHaveURL(/\/\?t=GRW-[A-Z0-9]{6}$/);
  return new URL(page.url()).searchParams.get("t")!;
}

test("ask, approve in the Queue tab, and the Ask tab shows the answer", async ({ page }) => {
  const code = await askOnPage(page, "What is the expense ratio of HDFC Mid Cap Fund?");
  await expect(page.getByText("Waiting for a person to approve this answer.")).toBeVisible({ timeout: 45_000 });
  await openTab(page, "Queue");
  const card = page.getByRole("tabpanel", { name: "Queue" }).getByRole("article", { name: code });
  await expect(card.getByText("review: pass")).toBeVisible({ timeout: 15_000 });
  await card.getByRole("button", { name: "Approve" }).click();
  await openTab(page, "Ask");
  await expect(page.getByRole("region", { name: "Answer" })).toContainText("Last checked", { timeout: 15_000 });
});

test("reject closes the ticket and Ask again brings the question back", async ({ page }) => {
  const text = "What is the exit load of HDFC Small Cap Fund?";
  const code = await askOnPage(page, text);
  await openTab(page, "Queue");
  const card = page.getByRole("tabpanel", { name: "Queue" }).getByRole("article", { name: code });
  await card.getByRole("button", { name: "Reject" }).click({ timeout: 45_000 });
  await openTab(page, "Ask");
  await expect(page.getByText("We couldn't answer this one.")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "Ask again" }).click();
  await expect(page.getByLabel("Your question", { exact: true })).toHaveValue(text);
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("region", { name: "How it works" })).toBeVisible();
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
  await openTab(page, "Queue");
  const card = page.getByRole("tabpanel", { name: "Queue" }).getByRole("article", { name: code });
  await expect(card.getByText("review: blocked")).toBeVisible();
  await expect(card.getByRole("button", { name: "Approve" })).toBeDisabled();
  await expect(card.getByText("Edit it first — the reviewer blocked this draft")).toBeVisible();
});

test("weekly approvals say exactly where they write, and fail safely without Google", async ({ page }) => {
  await page.goto("/");
  await openTab(page, "This week");
  const week = page.getByRole("tabpanel", { name: "This week" });
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
  await openTab(page, "Queue");
  const card = page.getByRole("tabpanel", { name: "Queue" }).getByRole("article", { name: code });
  await expect(card.getByText("Waiting for the desk…")).toBeVisible({ timeout: 15_000 });
  await expect(card.getByText(/review: /)).toBeVisible({ timeout: 45_000 });
  const shown = (await card.locator("p.whitespace-pre-line").first().textContent())!.trim();
  await card.getByRole("button", { name: "Edit" }).click();
  await expect(card.getByLabel("Edit reply")).toHaveValue(shown);
  expect(shown.length).toBeGreaterThan(10);
});

test("filters split the queue into Waiting, Answered and Closed", async ({ page, request }) => {
  const yes = await createTicket(request, "What is the benchmark of HDFC Large Cap Fund?");
  const no = await createTicket(request, "What is the riskometer level of HDFC Defence Fund?");
  await approveTicket(request, yes);
  await rejectTicket(request, no);
  await waitForStatus(request, yes, "answered");
  await waitForStatus(request, no, "closed");
  await page.goto("/?tab=queue");
  const queue = page.getByRole("tabpanel", { name: "Queue" });
  const show = queue.getByRole("radiogroup", { name: "Show" });
  await expect(show.getByRole("radio", { name: /^Waiting/ })).toBeChecked();
  await expect(queue.getByRole("article", { name: yes })).toHaveCount(0);
  await expect(queue.getByRole("article", { name: no })).toHaveCount(0);
  await show.getByRole("radio", { name: /^Answered/ }).click();
  await expect(queue.getByRole("article", { name: yes })).toBeVisible();
  await expect(queue.getByRole("article", { name: no })).toHaveCount(0);
  await show.getByRole("radio", { name: /^Closed/ }).click();
  await expect(queue.getByRole("article", { name: no })).toBeVisible();
  await expect(queue.getByRole("article", { name: yes })).toHaveCount(0);
});

test("Approve updates the card at once and reverts on a refusal", async ({ page, request }) => {
  const code = await createTicket(request, "What is the minimum SIP amount for HDFC Gilt Fund?");
  await waitForStatus(request, code, "in_review");
  await page.route("**/api/desk/actions/*/approve", async (route) => {
    await new Promise((r) => setTimeout(r, 1500));
    await route.fulfill({ status: 409, json: { detail: "This reply changed after you opened it — check it again." } });
  });
  await page.goto("/?tab=queue");
  const card = page.getByRole("tabpanel", { name: "Queue" }).getByRole("article", { name: code });
  await expect(card.getByText("review: pass")).toBeVisible({ timeout: 15_000 });
  await card.getByRole("button", { name: "Approve" }).click();
  await expect(card.getByText("approved", { exact: true })).toBeVisible({ timeout: 500 });
  await expect(card.getByRole("alert")).toHaveText("This reply changed after you opened it — check it again.");
  await expect(card.getByText("pending", { exact: true })).toBeVisible();
  await expect(card.getByRole("button", { name: "Approve" })).toBeVisible();
});

test("a Hindi draft says its translation is coming", async ({ page, request }) => {
  const code = await createTicket(request, "What is the expense ratio of HDFC Defence Fund?");
  await waitForStatus(request, code, "in_review");
  await page.route("**/api/desk/queue", async (route) => {
    const res = await route.fetch();
    const items = (await res.json()) as { code: string; draft: Record<string, unknown> | null }[];
    for (const i of items) if (i.code === code && i.draft) Object.assign(i.draft, { translation: null, translation_pending: true });
    await route.fulfill({ response: res, json: items });
  });
  await page.goto("/?tab=queue");
  const card = page.getByRole("tabpanel", { name: "Queue" }).getByRole("article", { name: code });
  await expect(card.getByText("Hindi translation coming…")).toBeVisible({ timeout: 15_000 });
});
