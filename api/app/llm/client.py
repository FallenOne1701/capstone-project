"""Groq-first JSON completion with Gemini fallback. Never raises; returns None on failure."""

from __future__ import annotations

import asyncio
import json
import logging

from app.config import get_settings
from app.llm.ratelimit import GroqRateLimiter

log = logging.getLogger(__name__)
_limiters: dict[str, GroqRateLimiter] = {}


def llm_enabled() -> bool:
    s = get_settings()
    return s.use_llm and bool(s.groq_api_key or s.google_api_key)


def _limiter(model: str) -> GroqRateLimiter:
    s = get_settings()
    if model not in _limiters:
        _limiters[model] = GroqRateLimiter(rpm=s.groq_rpm, tpm=s.groq_tpm)
    return _limiters[model]


def _gemini_timeout() -> float:
    return get_settings().gemini_timeout_s


async def _groq_call(model: str, system: str, user: str) -> str:
    from groq import AsyncGroq
    s = get_settings()
    if not s.groq_api_key:
        raise RuntimeError("no groq key")
    await asyncio.to_thread(_limiter(model).wait, GroqRateLimiter.estimate_tokens(system + user) + 400)
    resp = await AsyncGroq(api_key=s.groq_api_key).chat.completions.create(
        model=model, temperature=0, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    return resp.choices[0].message.content or ""


async def _gemini_call(system: str, user: str) -> str:
    from google import genai
    from google.genai import types
    s = get_settings()
    if not s.google_api_key:
        raise RuntimeError("no gemini key")
    client = genai.Client(api_key=s.google_api_key)
    resp = await client.aio.models.generate_content(
        model=s.gemini_model, contents=user,
        config=types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json", temperature=0),
    )
    return resp.text or ""


def _parse(raw: str) -> dict | None:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


async def complete_json(system: str, user: str, *, fast: bool = False) -> dict | None:
    if not llm_enabled():
        return None
    s = get_settings()
    model = s.groq_model_fast if fast else s.groq_model
    try:
        data = _parse(await _groq_call(model, system, user))
        if data is not None:
            return data
    except Exception as exc:  # noqa: BLE001
        log.warning("groq call failed: %s", type(exc).__name__)
    try:
        return _parse(await asyncio.wait_for(_gemini_call(system, user), timeout=_gemini_timeout()))
    except Exception as exc:  # noqa: BLE001
        log.warning("gemini fallback failed: %s", type(exc).__name__)
        return None
