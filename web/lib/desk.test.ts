import { describe, expect, it } from "vitest";
import { deskHref, parseTab, queueBucket, waitingCount, weeklyNeedsYou } from "./desk";
import type { Action } from "./types";

describe("parseTab", () => {
  it("passes week and queue", () => {
    expect(parseTab("queue")).toBe("queue");
    expect(parseTab("week")).toBe("week");
  });
  it("opens Ask for anything else", () => {
    expect(parseTab("xyz")).toBe("ask");
    expect(parseTab(undefined)).toBe("ask");
    expect(parseTab(null)).toBe("ask");
  });
  it("takes the first of repeated values", () => {
    expect(parseTab(["week", "queue"])).toBe("week");
  });
});

describe("deskHref", () => {
  it("never writes the Ask tab", () => {
    expect(deskHref("ask", null)).toBe("/");
    expect(deskHref("ask", "GRW-ABC123")).toBe("/?t=GRW-ABC123");
  });
  it("puts the ticket first, then the tab", () => {
    expect(deskHref("queue", null)).toBe("/?tab=queue");
    expect(deskHref("week", "GRW-ABC123")).toBe("/?t=GRW-ABC123&tab=week");
  });
  it("encodes the code", () => {
    expect(deskHref("ask", "A B&C")).toBe("/?t=A%20B%26C");
  });
});

describe("queueBucket", () => {
  it("answered and closed are their own; everything else waits", () => {
    expect(queueBucket({ status: "answered" })).toBe("answered");
    expect(queueBucket({ status: "closed" })).toBe("closed");
    expect(queueBucket({ status: "in_review" })).toBe("waiting");
    expect(queueBucket({ status: "failed" })).toBe("waiting");
    expect(queueBucket({ status: "received" })).toBe("waiting");
  });
});

describe("waitingCount", () => {
  it("is null when the queue could not load", () => {
    expect(waitingCount(null)).toBeNull();
  });
  it("counts waiting tickets", () => {
    expect(waitingCount([])).toBe(0);
    expect(waitingCount([{ status: "in_review" }, { status: "answered" }, { status: "failed" }])).toBe(2);
  });
});

describe("weeklyNeedsYou", () => {
  it("is true when a weekly write waits or failed", () => {
    expect(weeklyNeedsYou({ actions: [{ type: "doc_append", status: "pending" } as Action] })).toBe(true);
    expect(weeklyNeedsYou({ actions: [{ type: "email_draft", status: "failed" } as Action] })).toBe(true);
  });
  it("is false otherwise", () => {
    expect(weeklyNeedsYou(null)).toBe(false);
    expect(weeklyNeedsYou({ actions: [{ type: "email_draft", status: "executed" } as Action] })).toBe(false);
    expect(weeklyNeedsYou({ actions: [{ type: "reply_publish", status: "pending" } as Action] })).toBe(false);
  });
});
