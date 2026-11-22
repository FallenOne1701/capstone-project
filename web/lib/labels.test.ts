import { describe, expect, it } from "vitest";
import { actionTitle, EXAMPLE_QUESTIONS, progressSteps, ASK_AGAIN, nextPollMs, CLOSED_TEXT, clarifyQuestion, intentLabel, scopeNotice, statusLabel, waitingText, weekHeading } from "./labels";
import type { Preview } from "./types";

const base: Preview = {
  redacted_text: "exit load?", pii_types: [], intent: "fee_question", scheme_ids: [],
  language: "en", needs_clarification: false, options: [], scheme_names: [],
};

describe("intentLabel", () => {
  it("joins intent and the single scheme", () => {
    expect(intentLabel({ ...base, scheme_ids: ["m"], scheme_names: ["HDFC Mid Cap"] })).toBe("Fee question · HDFC Mid Cap");
  });
  it("shows only the intent when there is no single scheme", () => {
    expect(intentLabel(base)).toBe("Fee question");
    expect(intentLabel({ ...base, scheme_ids: ["a", "b"], scheme_names: ["A", "B"] })).toBe("Fee question");
  });
  it("labels every intent", () => {
    expect(intentLabel({ ...base, intent: "performance_request" })).toBe("Returns request");
  });
});

describe("clarifyQuestion", () => {
  it("asks between two schemes", () => {
    expect(clarifyQuestion(["HDFC Mid Cap", "HDFC Small Cap"])).toBe("HDFC Mid Cap or HDFC Small Cap?");
  });
  it("lists three schemes", () => {
    expect(clarifyQuestion(["A", "B", "C"])).toBe("A, B or C?");
  });
});

describe("statusLabel", () => {
  it("uses the public status words", () => {
    expect(statusLabel("received")).toBe("received");
    expect(statusLabel("in_review")).toBe("in review");
    expect(statusLabel("answered")).toBe("answered");
    expect(statusLabel("failed")).toBe("failed");
  });
});

describe("scopeNotice", () => {
  it("uses the facts-only notice for advice and returns", () => {
    expect(scopeNotice("advice_request")).toBe("We share facts only and can't advise on buying, selling or returns");
    expect(scopeNotice("performance_request")).toBe("We share facts only and can't advise on buying, selling or returns");
  });
  it("uses the off-topic notice for banking and other products", () => {
    expect(scopeNotice("out_of_scope")).toBe(
      "We only answer factual questions about HDFC mutual funds on Groww. We can't help with banking, loans, cards, insurance or other products, and we never give advice.");
  });
  it("has no notice for fund questions", () => {
    expect(scopeNotice("fee_question")).toBeNull();
  });
});

describe("weekHeading", () => {
  it("calls a recent pulse this week", () => {
    expect(weekHeading("2026-11-17", false)).toBe("This week · week ending 17 Nov 2026");
  });
  it("never calls an old pulse this week", () => {
    expect(weekHeading("2026-11-03", true)).toBe("Latest pulse · week ending 3 Nov 2026");
  });
});

describe("Plan 3c: who approves, closed tickets", () => {
  it("labels a closed ticket as closed", () => {
    expect(statusLabel("closed")).toBe("closed");
  });
  it("tells the asker a person approves when auto mode is off", () => {
    expect(waitingText("in_review", "person")).toBe("Waiting for a person to approve this answer.");
    expect(waitingText("in_review", "auto")).toBe("Our agents are checking the answer against official sources and the rules…");
  });
  it("gives the exact rejected copy", () => {
    expect(CLOSED_TEXT).toBe("We couldn't answer this one.");
    expect(ASK_AGAIN).toBe("Ask again");
  });
});

describe("actionTitle", () => {
  it("says the Gmail draft is not sent", () => {
    expect(actionTitle({ type: "email_draft", target_label: "Gmail draft to the product team (d***@x.com)" }))
      .toBe("Gmail draft to the product team (d***@x.com), not sent");
  });
  it("keeps the Doc target as the API states it", () => {
    expect(actionTitle({ type: "doc_append", target_label: "Append to the weekly pulse Google Doc (DOC1)" }))
      .toBe("Append to the weekly pulse Google Doc (DOC1)");
  });
});

describe("nextPollMs", () => {
  it("stops only on a final answer or a closed ticket", () => {
    expect(nextPollMs("answered")).toBeNull();
    expect(nextPollMs("closed")).toBeNull();
    expect(nextPollMs("in_review")).toBe(3000);
    expect(nextPollMs("received")).toBe(1000);   // the draft is moments away: check every second
  });
  it("keeps watching a failed ticket slowly while a person can re-run it", () => {
    expect(nextPollMs("failed")).toBe(15000);
  });
});

describe("progressSteps", () => {
  it("received: the question is in and the checks are running", () => {
    expect(progressSteps("received", "person")!.map((s) => s.state)).toEqual(["done", "current", "todo", "todo"]);
  });
  it("in review waits for a person after the checks", () => {
    expect(progressSteps("in_review", "person")).toEqual([
      { label: "Received", state: "done" }, { label: "Checked", state: "done" },
      { label: "Waiting for a person", state: "current" }, { label: "Answered", state: "todo" }]);
  });
  it("auto mode says Approving", () => {
    expect(progressSteps("in_review", "auto")![2].label).toBe("Approving");
  });
  it("answered is all done", () => {
    expect(progressSteps("answered", "person")!.every((s) => s.state === "done")).toBe(true);
  });
  it("closed and failed show no progress", () => {
    expect(progressSteps("closed", "person")).toBeNull();
    expect(progressSteps("failed", "person")).toBeNull();
  });
});

describe("EXAMPLE_QUESTIONS", () => {
  it("has three", () => {
    expect(EXAMPLE_QUESTIONS).toHaveLength(3);
  });
});
