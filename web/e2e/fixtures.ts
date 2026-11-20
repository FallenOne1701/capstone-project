import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const API = "http://localhost:8001";

export async function createTicket(request: APIRequestContext, text: string): Promise<string> {
  const r = await request.post(`${API}/api/ask`, { data: { text } });
  expect(r.ok()).toBeTruthy();
  return (await r.json()).code as string;
}

export async function waitForStatus(request: APIRequestContext, code: string, status: string): Promise<void> {
  await expect
    .poll(async () => (await (await request.get(`${API}/api/tickets/${code}`)).json()).status, { timeout: 45_000 })
    .toBe(status);
}

/** Human mode (AUTO_APPROVE=0): approve a ticket's pending reply the way the page does, via the open desk API. */
export async function approveTicket(request: APIRequestContext, code: string): Promise<void> {
  let actionId: number | undefined;
  let reply: string | undefined;
  await expect
    .poll(async () => {
      const items = (await (await request.get(`${API}/api/desk/queue`)).json()) as {
        code: string; action: { id: number; status: string } | null; draft: { reply: string } | null;
      }[];
      const item = items.find((i) => i.code === code);
      const a = item?.action;
      actionId = a && a.status === "pending" ? a.id : undefined;
      reply = item?.draft?.reply;
      return actionId !== undefined;
    }, { timeout: 45_000 })
    .toBe(true);
  const r = await request.post(`${API}/api/desk/actions/${actionId}/approve`, { data: { reply } });
  expect(r.ok()).toBeTruthy();
}

/** Opens one of the desk's tabs and waits until it is the selected one. */
export async function openTab(page: Page, name: "Ask" | "This week" | "Queue"): Promise<void> {
  const tab = page.getByRole("tab", { name: new RegExp(`^${name}`) });
  await tab.click();
  await expect(tab).toHaveAttribute("aria-selected", "true");
}
