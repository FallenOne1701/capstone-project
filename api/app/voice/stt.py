"""Whisper transcription. Audio bytes stay in memory; transcripts are never logged."""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel

from app.config import get_settings

log = logging.getLogger(__name__)
NO_SPEECH_MEAN = 0.6
_PROMPT = "Question about HDFC mutual funds on Groww, in English, Hindi or Hinglish."
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


class NoSpeech(Exception):
    """The clip was silent, empty, or Whisper invented text from noise."""


class VoiceUnavailable(Exception):
    """Voice is switched off, has no key, or the provider failed."""


class Transcript(BaseModel):
    text: str
    language: str  # whisper language name ("english", "hindi") or "hi" after an Urdu retry


def voice_enabled() -> bool:
    s = get_settings()
    return s.use_llm and bool(s.groq_api_key)


async def _whisper(audio: bytes, filename: str, language: str | None = None) -> dict:
    from groq import AsyncGroq
    s = get_settings()
    kw = dict(file=(filename, audio), model=s.groq_stt_model, response_format="verbose_json", temperature=0,
              prompt=_PROMPT)
    if language:
        kw["language"] = language
    resp = await AsyncGroq(api_key=s.groq_api_key).audio.transcriptions.create(**kw)
    return resp.model_dump() if hasattr(resp, "model_dump") else dict(resp)


def _check(payload: dict) -> str:
    text = (payload.get("text") or "").strip()
    probs = [seg.get("no_speech_prob", 0.0) for seg in payload.get("segments") or []]
    if not text or (probs and sum(probs) / len(probs) >= NO_SPEECH_MEAN):
        raise NoSpeech()
    return text


async def transcribe(audio: bytes, filename: str) -> Transcript:
    if not voice_enabled():
        raise VoiceUnavailable()
    try:
        payload = await _whisper(audio, filename, None)
        language = (payload.get("language") or "").lower()
        if language == "urdu":
            payload = await _whisper(audio, filename, "hi")
            language = "hi"
    except Exception as exc:  # noqa: BLE001
        log.warning("stt failed: %s", type(exc).__name__)
        raise VoiceUnavailable() from exc
    text = _check(payload)
    log.info("stt ok lang=%s chars=%d", language, len(text))
    return Transcript(text=text, language=language)


def language_hint(t: Transcript) -> str | None:
    """Whisper hears Hindi but the text is romanised → Hinglish (detect_language would miss short ones)."""
    if t.language == "hindi" and not _DEVANAGARI.search(t.text):
        return "hinglish"
    return None
