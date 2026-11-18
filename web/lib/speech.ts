import type { Language } from "./types";

export type SpeechLang = "en-IN" | "hi-IN";
export interface VoiceLike { lang: string; name: string }

/** Hindi voice only when there is a Hindi text to read. */
export function speechLang(language: Language, hasLocal: boolean): SpeechLang {
  return hasLocal && (language === "hi" || language === "hinglish") ? "hi-IN" : "en-IN";
}

const norm = (l: string) => l.replace("_", "-").toLowerCase();
const prefix = (l: string) => norm(l).split("-")[0];

/**
 * Best voice for `want`: exact → same language → Indian English → any English → none.
 * `fellBack` is true when the voice speaks a different language than wanted (e.g. no Hindi voice).
 */
export function pickVoice<V extends VoiceLike>(voices: V[], want: SpeechLang): { voice: V | null; fellBack: boolean } {
  const voice =
    voices.find((v) => norm(v.lang) === norm(want)) ??
    voices.find((v) => prefix(v.lang) === prefix(want)) ??
    voices.find((v) => norm(v.lang) === "en-in") ??
    voices.find((v) => prefix(v.lang) === "en") ??
    null;
  return { voice, fellBack: prefix(voice?.lang ?? "en") !== prefix(want) };
}

interface SynthLike<V> {
  getVoices(): V[];
  addEventListener(type: "voiceschanged", cb: () => void): void;
  removeEventListener(type: "voiceschanged", cb: () => void): void;
}

/** Chrome fills getVoices() asynchronously: wait for voiceschanged, or give up after `timeoutMs`. */
export function loadVoices<V>(synth: SynthLike<V>, timeoutMs = 1500): Promise<V[]> {
  const now = synth.getVoices();
  if (now.length) return Promise.resolve(now);
  return new Promise((resolve) => {
    const done = () => {
      clearTimeout(timer);
      synth.removeEventListener("voiceschanged", done);
      resolve(synth.getVoices());
    };
    const timer = setTimeout(done, timeoutMs);
    synth.addEventListener("voiceschanged", done);
  });
}

/** What to say and with which voice; with no Hindi voice the English text is read instead (and flagged). */
export function planSpeech<V extends VoiceLike>(voices: V[], want: SpeechLang, text: string, englishText: string) {
  const { voice, fellBack } = pickVoice(voices, want);
  if (!fellBack) return { voice, text, lang: want, fellBack };
  return { voice: pickVoice(voices, "en-IN").voice, text: englishText, lang: "en-IN" as SpeechLang, fellBack };
}
