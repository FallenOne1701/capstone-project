import { expect, type APIRequestContext } from "@playwright/test";

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
  await expect
    .poll(async () => {
      const items = (await (await request.get(`${API}/api/desk/queue`)).json()) as {
        code: string; action: { id: number; status: string } | null;
      }[];
      const a = items.find((i) => i.code === code)?.action;
      actionId = a && a.status === "pending" ? a.id : undefined;
      return actionId !== undefined;
    }, { timeout: 45_000 })
    .toBe(true);
  const r = await request.post(`${API}/api/desk/actions/${actionId}/approve`);
  expect(r.ok()).toBeTruthy();
}
