"""Voice transcription endpoint: in-memory only, silence/hallucination and Urdu-script guards (Plan 3 Task 1)."""

import builtins
import logging
import tempfile

import pytest

from app.voice import stt

FAIL = "Couldn't hear that — try again or type"
UNAVAILABLE = "Voice is unavailable right now — please type your question."


def _payload(text, *, language="english", no_speech=0.05):
    return {"text": text, "language": language,
            "segments": [{"text": text, "no_speech_prob": no_speech}] if text.strip() else []}


@pytest.fixture()
def whisper(monkeypatch):
    calls = []
    replies = []

    async def fake(audio, filename, language=None):
        calls.append({"audio": audio, "filename": filename, "language": language})
        return replies.pop(0) if len(replies) > 1 else replies[0]

    monkeypatch.setattr(stt, "_whisper", fake)
    monkeypatch.setattr(stt, "voice_enabled", lambda: True)
    return calls, replies


def _post(client, *, size=20_000, duration_ms=2500):
    return client.post("/api/voice/transcribe", files={"audio": ("q.webm", b"\x1a" * size, "audio/webm")},
                       data={"duration_ms": str(duration_ms)})


def test_transcribe_returns_redacted_preview(client, whisper, caplog):
    calls, replies = whisper
    replies.append(_payload("my pan is ABCDE1234F what is the exit load of HDFC mid cap"))
    with caplog.at_level(logging.DEBUG):
        r = _post(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "[PAN]" in body["redacted_text"] and "ABCDE1234F" not in body["redacted_text"]
    assert body["intent"] == "fee_question"
    assert body["scheme_names"] == ["HDFC Mid Cap"]
    assert len(calls) == 1
    assert not any("ABCDE1234F" in rec.getMessage() for rec in caplog.records)


def test_too_short_clip_rejected(client, whisper):
    calls, _ = whisper
    r = _post(client, duration_ms=600)
    assert r.status_code == 422 and r.json()["detail"] == FAIL
    assert calls == []


def test_too_long_clip_rejected(client, whisper):
    calls, _ = whisper
    r = _post(client, duration_ms=61001)
    assert r.status_code == 422 and r.json()["detail"] == FAIL
    assert calls == []


def test_oversize_upload_rejected(client, whisper):
    calls, _ = whisper
    r = _post(client, size=5_000_001)
    assert r.status_code == 413
    assert calls == []


def test_silence_hallucination_rejected(client, whisper):
    _, replies = whisper
    replies.append(_payload("Thank you.", no_speech=0.9))
    r = _post(client)
    assert r.status_code == 422 and r.json()["detail"] == FAIL


def test_empty_text_rejected(client, whisper):
    _, replies = whisper
    replies.append(_payload("  "))
    r = _post(client)
    assert r.status_code == 422 and r.json()["detail"] == FAIL


def test_urdu_script_retried_as_hindi(client, whisper):
    calls, replies = whisper
    replies += [_payload("ایچ ڈی ایف سی مڈ کیپ کا ایگزٹ لوڈ کیا ہے", language="urdu"),
                _payload("एचडीएफसी मिड कैप का एग्जिट लोड क्या है", language="hindi")]
    r = _post(client)
    assert r.status_code == 200, r.text
    assert [c["language"] for c in calls] == [None, "hi"]
    assert "एग्जिट" in r.json()["redacted_text"]
    assert r.json()["language"] == "hi"


def test_romanised_hindi_marked_hinglish(client, whisper):
    _, replies = whisper
    replies.append(_payload("HDFC mid cap exit load", language="hindi"))
    r = _post(client)
    assert r.status_code == 200 and r.json()["language"] == "hinglish"


def test_voice_unavailable_without_llm(client):
    r = _post(client)   # conftest: USE_LLM=0
    assert r.status_code == 503 and r.json()["detail"] == UNAVAILABLE


def test_provider_error_is_unavailable(client, monkeypatch):
    async def boom(audio, filename, language=None):
        raise RuntimeError("groq down")
    monkeypatch.setattr(stt, "_whisper", boom)
    monkeypatch.setattr(stt, "voice_enabled", lambda: True)
    r = _post(client)
    assert r.status_code == 503 and r.json()["detail"] == UNAVAILABLE


def test_large_clip_stays_in_memory(client, whisper, monkeypatch):
    # Starlette spools uploads over 1 MB to a temp file on disk; a 60 s clip can exceed that.
    _, replies = whisper
    replies.append(_payload("what is the exit load of HDFC mid cap"))

    def no_rollover(self):
        raise AssertionError("upload rolled over to disk")

    monkeypatch.setattr(tempfile.SpooledTemporaryFile, "rollover", no_rollover)
    r = _post(client, size=2_000_000)
    assert r.status_code == 200, r.text


def test_audio_never_written_to_disk(client, whisper, monkeypatch):
    _, replies = whisper
    replies.append(_payload("what is the exit load of HDFC mid cap"))
    real_open = builtins.open

    def guarded_open(file, mode="r", *a, **k):
        if any(c in mode for c in "wax+"):
            raise AssertionError(f"write attempted: {file}")
        return real_open(file, mode, *a, **k)

    def no_temp(*a, **k):
        raise AssertionError("tempfile used")

    monkeypatch.setattr(builtins, "open", guarded_open)
    for name in ("TemporaryFile", "NamedTemporaryFile", "SpooledTemporaryFile", "mkstemp", "mkdtemp"):
        monkeypatch.setattr(tempfile, name, no_temp)
    r = _post(client)
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("text", ["Thank you.", " thank you ", "Thanks for watching!", "you", "Bye.",
                                  "Subtitles by the Amara.org community", "धन्यवाद।"])
def test_known_whisper_phantoms_rejected_even_with_zero_no_speech_prob(client, whisper, text):
    # Groq reports no_speech_prob 0 for silent clips (seen live), so the phrase itself must be caught
    _, replies = whisper
    replies.append(_payload(text, no_speech=0.0))
    r = _post(client)
    assert r.status_code == 422 and r.json()["detail"] == FAIL


def test_real_question_mentioning_thanks_is_kept(client, whisper):
    _, replies = whisper
    replies.append(_payload("Thank you. What is the exit load of HDFC mid cap?", no_speech=0.0))
    assert _post(client).status_code == 200


@pytest.mark.parametrize("text", [
    "Thank you. Thank you.", "Thank you. Bye.", "Thanks for watching and please subscribe.",
    "Question about HDFC mutual funds on Groww, in English, Hindi or Hinglish.",   # Whisper echoing its prompt
    "Question about HDFC mutual funds on Groww",
])
def test_repeated_phantoms_and_prompt_echo_rejected(client, whisper, text):
    _, replies = whisper
    replies.append(_payload(text, no_speech=0.0))
    r = _post(client)
    assert r.status_code == 422 and r.json()["detail"] == FAIL


def test_upload_without_content_length_is_capped(client, whisper):
    calls, _ = whisper
    boundary = "xyzBOUNDARY"
    head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"duration_ms\"\r\n\r\n2500\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"audio\"; filename=\"q.webm\"\r\n"
            "Content-Type: audio/webm\r\n\r\n").encode()

    def body():   # a generator body is sent chunked, with no Content-Length header
        yield head
        for _ in range(7):
            yield b"\x1a" * 1_000_000
        yield f"\r\n--{boundary}--\r\n".encode()

    r = client.post("/api/voice/transcribe", content=body(),
                    headers={"content-type": f"multipart/form-data; boundary={boundary}"})
    assert r.status_code == 413
    assert calls == []


def test_capped_stream_stops_reading_past_the_limit():
    import asyncio

    from fastapi import HTTPException

    from app.api.public import _capped
    pulled = []

    async def source():
        for i in range(7):
            pulled.append(i)
            yield b"x" * 1_000_000

    async def drain():
        async for _ in _capped(source(), 5_000_000):
            pass

    with pytest.raises(HTTPException) as e:
        asyncio.run(drain())
    assert e.value.status_code == 413
    assert len(pulled) == 6   # stopped as soon as the limit was crossed, not after reading everything
