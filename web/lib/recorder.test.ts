import { describe, expect, it } from "vitest";
import { formatClock, MAX_MS, MIN_MS, pickMimeType, voiceSupport } from "./recorder";

describe("pickMimeType", () => {
  it("prefers webm/opus", () => {
    expect(pickMimeType(() => true)).toBe("audio/webm;codecs=opus");
  });
  it("falls back to mp4 on Safari/iOS", () => {
    expect(pickMimeType((t) => t === "audio/mp4")).toBe("audio/mp4");
  });
  it("returns null when nothing is supported", () => {
    expect(pickMimeType(() => false)).toBeNull();
  });
});

describe("voiceSupport", () => {
  it("is ok on a secure page with a recorder", () => {
    expect(voiceSupport({ secure: true, hasMediaDevices: true, hasRecorder: true })).toBe("ok");
  });
  it("needs a secure page", () => {
    expect(voiceSupport({ secure: false, hasMediaDevices: false, hasRecorder: true })).toBe("insecure");
  });
  it("is unsupported without MediaRecorder or mediaDevices", () => {
    expect(voiceSupport({ secure: true, hasMediaDevices: true, hasRecorder: false })).toBe("unsupported");
    expect(voiceSupport({ secure: true, hasMediaDevices: false, hasRecorder: true })).toBe("unsupported");
  });
});

describe("limits and clock", () => {
  it("caps at 60 s and rejects under 1 s", () => {
    expect(MAX_MS).toBe(60_000);
    expect(MIN_MS).toBe(1_000);
  });
  it("formats the live timer", () => {
    expect(formatClock(7_400)).toBe("0:07");
    expect(formatClock(60_000)).toBe("1:00");
  });
});
