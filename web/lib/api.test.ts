import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, approve, ask, deskQueue, editDraft } from "./api";

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

describe("desk api (Plan 3c)", () => {
  it("approves on the open desk route with no console key", async () => {
    const f = mockFetch(200, { id: 7, status: "executed" });
    await approve(7);
    expect(f.mock.calls[0][0]).toMatch(/\/api\/desk\/actions\/7\/approve$/);
    expect(f.mock.calls[0][1]?.method).toBe("POST");
    expect(new Headers(f.mock.calls[0][1]?.headers).get("X-Console-Key")).toBeNull();
  });

  it("posts an edit as JSON", async () => {
    const f = mockFetch(200, {});
    await editDraft(3, "x");
    expect(f.mock.calls[0][0]).toMatch(/\/api\/desk\/drafts\/3\/edit$/);
    expect(JSON.parse(f.mock.calls[0][1]!.body as string)).toEqual({ reply: "x" });
  });

  it("reads the queue from the desk", async () => {
    const f = mockFetch(200, []);
    await deskQueue();
    expect(f.mock.calls[0][0]).toMatch(/\/api\/desk\/queue$/);
  });
});

describe("approve sends what the person saw (Plan 3c review)", () => {
  it("includes the reviewed reply", async () => {
    const f = mockFetch(200, { id: 7, status: "executed" });
    await approve(7, "The expense ratio is 0.77%.");
    expect(JSON.parse(f.mock.calls[0][1]!.body as string)).toEqual({ reply: "The expense ratio is 0.77%." });
  });
});
