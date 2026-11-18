import { describe, expect, it } from "vitest";
import { clarifyQuestion, intentLabel, statusLabel } from "./labels";
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
