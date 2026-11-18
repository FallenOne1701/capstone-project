import { expect, type APIRequestContext } from "@playwright/test";

export const API = "http://localhost:8001";
export const CONSOLE_PASSWORD = "e2e-pass-123";
export const CONSOLE_HEADERS = { "X-Console-Key": CONSOLE_PASSWORD };

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
