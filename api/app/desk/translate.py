"""Hindi version of an approved-to-be reply. Checked by invariants: the facts and links must not move."""

from __future__ import annotations

import re
from collections import Counter

from app.guard.pii import find_pii
from app.llm.client import complete_json

_URL = re.compile(r"https?://[^\s)\]>\"']+")
_NUM = re.compile(r"\d+(?:[.,]\d+)*")
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_SYSTEM = (
    "Translate this mutual-fund support reply into simple, polite Hindi in Devanagari script. Keep these exactly as "
    "they are, character for character: every URL, every number and percentage, every date, every scheme name "
    "(e.g. 'HDFC Mid Cap Fund'), and the labels 'Source:' and 'Last checked:'. Do not add or remove any fact, "
    "advice or link. Return JSON {\"text\": \"...\"}."
)


def _urls(t: str) -> set[str]:
    return {u.rstrip(".,;") for u in _URL.findall(t)}


def _nums(t: str) -> Counter:
    return Counter(_NUM.findall(_URL.sub(" ", t)))


def validate_translation(src: str, out: str) -> list[str]:
    probs: list[str] = []
    if _urls(src) != _urls(out):
        probs.append("links changed")
    if _nums(src) != _nums(out):
        probs.append("numbers changed")
    if find_pii(out):
        probs.append("contains PII")
    if not _DEVANAGARI.search(out):
        probs.append("not in Devanagari")
    if len(out) > 3 * len(src):
        probs.append("too long")
    return probs


async def translate_reply(reply: str) -> str | None:
    data = await complete_json(_SYSTEM, reply)
    text = (data or {}).get("text")
    return text.strip() if isinstance(text, str) and text.strip() else None
