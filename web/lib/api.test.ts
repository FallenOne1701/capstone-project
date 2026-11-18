import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, checkKey } from "./api";

const store = new Map<string, string>();

beforeEach(() => {
  store.clear();
  vi.stubGlobal("sessionStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
  });
});
afterEach(() => vi.unstubAllGlobals());

function mockFetch(status: number, body: unknown) {
  // typed (url, init) so tests can read mock.calls[0][1]
  const f = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async () =>
    new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));
  vi.stubGlobal("fetch", f);
  return f;
}

function headersOf(f: ReturnType<typeof mockFetch>): Headers {
  const init = f.mock.calls[0][1] as RequestInit;
  return new Headers(init.headers);
}

describe("api", () => {
  it("sends the console key only on console calls", async () => {
    store.set("consoleKey", "secret");
    let f = mockFetch(200, {});
    await api("/api/tickets/GRW-1");
    expect(headersOf(f).get("X-Console-Key")).toBeNull();
    f = mockFetch(200, []);
    await api("/api/console/queue", undefined, { console: true });
    expect(headersOf(f).get("X-Console-Key")).toBe("secret");
  });

  it("maps FastAPI detail into ApiError", async () => {
    mockFetch(422, { detail: "Couldn't hear that — try again or type" });
    const err = (await api("/api/ask/preview", { method: "POST" }).catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(422);
    expect(err.detail).toBe("Couldn't hear that — try again or type");
  });

  it("checkKey is false on 401 and true on 200", async () => {
    mockFetch(401, { detail: "bad" });
    expect(await checkKey("nope")).toBe(false);
    const f = mockFetch(200, []);
    expect(await checkKey("ok")).toBe(true);
    expect(headersOf(f).get("X-Console-Key")).toBe("ok");
  });
});

describe("console session", () => {
  it("a 401 on a console call clears the stored key", async () => {
    store.set("consoleKey", "old");
    mockFetch(401, { detail: "console key required" });
    await api("/api/console/queue", undefined, { console: true }).catch(() => null);
    expect(store.has("consoleKey")).toBe(false);
  });
});
