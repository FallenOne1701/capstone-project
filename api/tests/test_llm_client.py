import asyncio

from app.llm import client as c


def test_disabled_returns_none(monkeypatch):
    monkeypatch.setattr(c, "llm_enabled", lambda: False)
    assert asyncio.run(c.complete_json("s", "u")) is None


def test_groq_success_parses_json(monkeypatch):
    monkeypatch.setattr(c, "llm_enabled", lambda: True)

    async def fake_groq(model, system, user):
        return '{"ok": true}'
    monkeypatch.setattr(c, "_groq_call", fake_groq)
    assert asyncio.run(c.complete_json("s", "u")) == {"ok": True}


def test_groq_failure_falls_back_to_gemini(monkeypatch):
    monkeypatch.setattr(c, "llm_enabled", lambda: True)

    async def boom(model, system, user):
        raise RuntimeError("429 rate limited")

    async def fake_gemini(system, user):
        return '{"via": "gemini"}'
    monkeypatch.setattr(c, "_groq_call", boom)
    monkeypatch.setattr(c, "_gemini_call", fake_gemini)
    assert asyncio.run(c.complete_json("s", "u")) == {"via": "gemini"}


def test_gemini_timeout_returns_none(monkeypatch):
    monkeypatch.setattr(c, "llm_enabled", lambda: True)
    monkeypatch.setattr(c, "_gemini_timeout", lambda: 0.05)

    async def boom(model, system, user):
        raise RuntimeError("down")

    async def slow(system, user):
        await asyncio.sleep(1)
        return "{}"
    monkeypatch.setattr(c, "_groq_call", boom)
    monkeypatch.setattr(c, "_gemini_call", slow)
    assert asyncio.run(c.complete_json("s", "u")) is None


def test_non_json_returns_none(monkeypatch):
    monkeypatch.setattr(c, "llm_enabled", lambda: True)

    async def junk(model, system, user):
        return "not json"

    async def none_gemini(system, user):
        return "still not json"
    monkeypatch.setattr(c, "_groq_call", junk)
    monkeypatch.setattr(c, "_gemini_call", none_gemini)
    assert asyncio.run(c.complete_json("s", "u")) is None
