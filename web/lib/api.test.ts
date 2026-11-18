import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, ask } from "./api";

afterEach(() => vi.unstubAllGlobals());

function mockFetch(status: number, body: unknown) {
  // typed (url, init) so tests can read mock.calls[0]
  const f = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async () =>
    new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));
  vi.stubGlobal("fetch", f);
  return f;
}

describe("api", () => {
  it("never sends a console key from the public page", async () => {
    const f = mockFetch(200, {});
    await api("/api/tickets/GRW-1");
    expect(new Headers(f.mock.calls[0][1]?.headers).get("X-Console-Key")).toBeNull();
  });

  it("posts JSON", async () => {
    const f = mockFetch(200, { code: "GRW-1", status: "received", notice: null });
    await ask({ text: "hi", channel: "text" });
    const init = f.mock.calls[0][1]!;
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("content-type")).toBe("application/json");
    expect(JSON.parse(init.body as string)).toEqual({ text: "hi", channel: "text" });
  });

  it("maps FastAPI detail into ApiError", async () => {
    mockFetch(429, { detail: "You've asked a lot of questions quickly — please wait a few minutes." });
    const err = (await api("/api/ask", { method: "POST" }).catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(429);
    expect(err.detail).toBe("You've asked a lot of questions quickly — please wait a few minutes.");
  });
});
