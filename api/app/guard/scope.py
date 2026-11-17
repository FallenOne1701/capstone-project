"""Output scope filter: facts-only, no advice, no performance figures, hard caps."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.guard.pii import find_pii

Kind = Literal["reply", "pulse", "explainer"]
CAPS = {"reply": ("sentences", 3), "pulse": ("words", 250), "explainer": ("bullets", 6)}


@dataclass(frozen=True)
class Violation:
    check: str
    detail: str


_ADVICE_PHRASES = re.compile(
    r"(?i)\b(you should|we recommend|i recommend|we suggest|i suggest|"
    r"consider (?:buying|selling|switching|investing|staying)|good time to|"
    r"better to (?:buy|sell|invest|switch)|worth investing|stay invested|must invest)\b"
)
_ADVICE_VERBS = re.compile(r"(?i)\b(buy|sell|hold|switch)\b")
_PERF_WORDS = re.compile(r"(?i)\b(cagr|xirr|annuali[sz]ed|performance|outperform\w*|underperform\w*)\b")
# "returns" is a claim only with a figure or a claim word nearby; official objectives say
# "seeks to generate reasonable returns", which is allowed.
_RETURN_WORD = re.compile(
    r"(?i)(?:\b(?:expected|guaranteed|assured|high|higher|highest|best|good|great|strong|past|last|annual|"
    r"annuali[sz]ed|yearly|monthly|average|gave|delivered|earned|kitna)\b(?:\W+\w+){0,3}?\W+returns?\b)|"
    r"(?:\breturns?\b(?:\W+\w+){0,3}?\W+(?:of\s+)?\d)|"
    r"(?:\breturns?\b(?:\W+\w+){0,2}?\W+(?:are|were|is|was)\s+(?:high|higher|good|great|strong|guaranteed|assured))"
)
_TRI = re.compile(r"(?i)\btotal return index\b|\bTRI\b")
# "Growth" in plan names ("Direct Growth", "Plan Growth", "Growth option") is not a performance claim.
_PLAN_GROWTH = re.compile(r"(?i)\b(?:direct|regular|plan)\s+growth\b|\bgrowth\s+(?:option|plan)\b")
_PCT_NEAR_GAIN = re.compile(
    r"(?i)(\d+(?:\.\d+)?\s?%(?:\W+\w+){0,6}?\W+(?:return\w*|gain\w*|grew|growth|gave|delivered|yield\w*))|"
    r"((?:return\w*|gain\w*|grew|growth|gave|delivered|yield\w*)(?:\W+\w+){0,6}?\W+\d+(?:\.\d+)?\s?%)"
)
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\[(\"'₹])")
_BULLET = re.compile(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+")


def detect_advice(text: str) -> bool:
    return bool(_ADVICE_PHRASES.search(text) or _ADVICE_VERBS.search(text))


def detect_performance(text: str) -> bool:
    if _PERF_WORDS.search(text):
        return True
    without_tri = _PLAN_GROWTH.sub(" ", _TRI.sub(" ", text))
    if _RETURN_WORD.search(without_tri):
        return True
    return bool(_PCT_NEAR_GAIN.search(without_tri))


def sentence_count(text: str) -> int:
    t = text.strip()
    return len([p for p in _SENT_SPLIT.split(t) if p.strip()]) if t else 0


def word_count(text: str) -> int:
    return len(text.split())


def bullet_count(text: str) -> int:
    return len(_BULLET.findall(text))


def check_output(text: str, *, kind: Kind) -> list[Violation]:
    out: list[Violation] = []
    if detect_advice(text):
        out.append(Violation("advice", "advice or buy/sell language"))
    if detect_performance(text):
        out.append(Violation("performance", "return or performance figure"))
    pii = find_pii(text)
    if pii:
        out.append(Violation("pii", f"residual PII: {', '.join(pii)}"))
    unit, cap = CAPS[kind]
    n = {"sentences": sentence_count, "words": word_count, "bullets": bullet_count}[unit](text)
    if n > cap:
        out.append(Violation("shape", f"{kind} has {n} {unit} (cap {cap})"))
    return out


def truncate_sentences(text: str, limit: int = 3) -> str:
    parts = [p.strip() for p in _SENT_SPLIT.split(text.strip()) if p.strip()]
    return " ".join(parts[:limit])


def strip_advice_and_performance(text: str) -> str:
    parts = [p.strip() for p in _SENT_SPLIT.split(text.strip()) if p.strip()]
    kept = [p for p in parts if not detect_advice(p) and not detect_performance(p)]
    return " ".join(kept)
