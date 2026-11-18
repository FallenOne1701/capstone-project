import { describe, expect, it } from "vitest";
import { loadVoices, pickVoice, planSpeech, speechLang } from "./speech";

const v = (lang: string, name = lang) => ({ lang, name });

describe("speechLang", () => {
  it("reads Hindi only when a Hindi text exists", () => {
    expect(speechLang("hi", true)).toBe("hi-IN");
    expect(speechLang("hinglish", true)).toBe("hi-IN");
    expect(speechLang("hi", false)).toBe("en-IN");
    expect(speechLang("en", false)).toBe("en-IN");
  });
});

describe("pickVoice", () => {
  it("takes the exact language", () => {
    expect(pickVoice([v("en-US"), v("hi-IN", "Lekha")], "hi-IN")).toEqual({ voice: v("hi-IN", "Lekha"), fellBack: false });
  });
  it("accepts the same language in another form", () => {
    expect(pickVoice([v("en-US"), v("hi_IN", "Google")], "hi-IN")).toEqual({ voice: v("hi_IN", "Google"), fellBack: false });
  });
  it("falls back to Indian English and says so", () => {
    expect(pickVoice([v("en-US"), v("en-IN", "Rishi")], "hi-IN")).toEqual({ voice: v("en-IN", "Rishi"), fellBack: true });
  });
  it("falls back to any English", () => {
    expect(pickVoice([v("fr-FR"), v("en-GB")], "en-IN")).toEqual({ voice: v("en-GB"), fellBack: false });
    expect(pickVoice([v("en-GB")], "hi-IN")).toEqual({ voice: v("en-GB"), fellBack: true });
  });
  it("returns null with no voices", () => {
    expect(pickVoice([], "en-IN")).toEqual({ voice: null, fellBack: false });
    expect(pickVoice([], "hi-IN")).toEqual({ voice: null, fellBack: true });
  });
});

describe("loadVoices", () => {
  it("returns voices at once when already loaded", async () => {
    const synth = { getVoices: () => [v("en-IN")], addEventListener() {}, removeEventListener() {} };
    expect(await loadVoices(synth, 50)).toEqual([v("en-IN")]);
  });
  it("waits for voiceschanged (Chrome loads voices late)", async () => {
    let list: { lang: string; name: string }[] = [];
    let cb: (() => void) | null = null;
    const synth = {
      getVoices: () => list,
      addEventListener: (_: string, f: () => void) => { cb = f; },
      removeEventListener() {},
    };
    const p = loadVoices(synth, 1000);
    list = [v("hi-IN")];
    cb!();
    expect(await p).toEqual([v("hi-IN")]);
  });
  it("gives up after the timeout", async () => {
    const synth = { getVoices: () => [], addEventListener() {}, removeEventListener() {} };
    expect(await loadVoices(synth, 20)).toEqual([]);
  });
});

describe("planSpeech", () => {
  const en = { lang: "en-IN", name: "Rishi" };
  const hi = { lang: "hi-IN", name: "Lekha" };
  it("reads the Hindi text with a Hindi voice", () => {
    expect(planSpeech([en, hi], "hi-IN", "हिंदी", "English")).toEqual({ voice: hi, text: "हिंदी", lang: "hi-IN", fellBack: false });
  });
  it("with no Hindi voice, reads the English text in English", () => {
    expect(planSpeech([en], "hi-IN", "हिंदी", "English")).toEqual({ voice: en, text: "English", lang: "en-IN", fellBack: true });
  });
  it("reads English as is", () => {
    expect(planSpeech([en], "en-IN", "English", "English")).toEqual({ voice: en, text: "English", lang: "en-IN", fellBack: false });
  });
});
