"""Weekly pulse: deterministic template over themes, verbatim quotes, repeated questions, fee confusion."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from app.config import get_settings
from app.guard.pii import find_pii
from app.guard.scope import check_output, detect_advice, detect_performance, word_count
from app.llm.client import complete_json, llm_enabled
from app.weekly.fee_topics import TOPIC_LABELS, FeeConfusion
from app.weekly.vocab import DEFAULT_ACTIONS, keyword_scores


@dataclass
class Quote:
    review_id: str
    theme_id: str
    text: str


def _safe(t: str) -> bool:
    return not (detect_advice(t) or detect_performance(t) or find_pii(t))


def _cut(t: str, n: int) -> str:
    w = t.split()
    return t if len(w) <= n else " ".join(w[:n]) + "…"


def select_quotes(themes, reviews_by_id, *, max_words: int = 24) -> list[Quote]:
    out: list[Quote] = []
    for t in themes[:3]:
        cands = [reviews_by_id[i] for i in t.review_ids if i in reviews_by_id and _safe(reviews_by_id[i].text_redacted)]
        low = [r for r in cands if r.rating <= 2] or cands
        # Best evidence for the theme: most theme keywords, readable length, then most recent.
        low = [r for r in low if 6 <= len(r.text_redacted.split()) <= 80] or low
        if low:
            r = max(low, key=lambda r: (keyword_scores(r.text_redacted)[t.theme_id], r.date, r.id))
            out.append(Quote(r.id, t.theme_id, _cut(r.text_redacted, max_words)))
    return out


_ACT_SYSTEM = (
    "You are writing exactly 3 internal action ideas for Groww's product and support teams, grounded only in the "
    "themes and quotes given. Each is one sentence starting with a verb (Audit, Trace, Clarify, Reduce...). No "
    "investment advice, no return figures, no PII. Return JSON {\"actions\": [\"...\", \"...\", \"...\"]}."
)


async def action_ideas(themes, quotes) -> tuple[list[str], int]:
    defaults = [DEFAULT_ACTIONS[t.theme_id] for t in themes[:3]]
    defaults += [a for a in DEFAULT_ACTIONS.values() if a not in defaults]
    defaults = defaults[:3]
    if not llm_enabled():
        return defaults, 0
    user = "\n".join([f"Theme {t.rank}: {t.label} ({t.count} reviews)" for t in themes[:3]] +
                     [f'Quote: "{q.text}"' for q in quotes])
    data = await complete_json(_ACT_SYSTEM, user)
    acts = [a.strip() for a in (data or {}).get("actions", []) if isinstance(a, str) and a.strip()]
    ok = len(acts) == 3 and all(not [v for v in check_output(a, kind="pulse") if v.check != "shape"] for a in acts)
    return (acts if ok else defaults), 1


def _render(*, week_end, window_start, window_end, review_count, themes, quotes, repeated, fee, actions,
            threshold) -> str:
    themed = sum(t.count for t in themes)
    L = [f"# Groww Weekly Review Pulse — week ending {week_end.isoformat()}",
         f"{review_count} Play Store reviews, {window_start.isoformat()} to {window_end.isoformat()}; "
         f"{themed} matched a theme.", "",
         "## Top themes"]
    L += [f"{t.rank}. {t.label} — {t.count} reviews ({t.recent_count} in last 7 days)" for t in themes[:3]]
    if len(themes) < 3:
        L.append(f"(Only {len(themes)} theme(s) had reviews in this window.)")
    L += ["", "## What users said"] + [f'- "{q.text}" ({q.review_id})' for q in quotes]
    head = "## Asked repeatedly"
    if repeated:
        head += f" ({repeated[0].window_start.isoformat()} to {repeated[0].window_end.isoformat()})"
    L += ["", head]
    L += [f"- {r.label}: {r.count} questions" for r in repeated] or \
         [f"- No question reached {threshold} asks in the last 7 days."]
    ev = fee.evidence
    L += ["", "## Fee confusion",
          f"- {TOPIC_LABELS[fee.topic]}: {ev['reviews']} reviews and {ev['tickets']} questions → explainer below.",
          "", "## Action ideas"] + [f"{i}. {a}" for i, a in enumerate(actions[:3], 1)]
    return "\n".join(L)


def compose_pulse(*, week_end: date, window_start: date, window_end: date, review_count: int, themes, quotes,
                  repeated, fee: FeeConfusion, actions: list[str]) -> str:
    args = dict(week_end=week_end, window_start=window_start, window_end=window_end, review_count=review_count,
                themes=themes, fee=fee, actions=actions, threshold=get_settings().repeat_threshold)
    text = _render(quotes=quotes, repeated=repeated, **args)
    if word_count(text) > 250:
        short = [Quote(q.review_id, q.theme_id, _cut(q.text.rstrip("…"), 14)) for q in quotes]
        text = _render(quotes=short, repeated=repeated, **args)
        if word_count(text) > 250:
            text = _render(quotes=short, repeated=repeated[:3], **args)
    return text


def validate_pulse(text: str) -> list[str]:
    probs: list[str] = []
    n = word_count(text)
    if n > 250:
        probs.append(f"pulse has {n} words (cap 250)")
    m = re.search(r"## Action ideas\n((?:\d+\..*\n?)+)", text)
    if not m or len(re.findall(r"(?m)^\d+\.", m.group(1))) != 3:
        probs.append("pulse must have exactly 3 action ideas")
    body = "\n".join(line for line in text.splitlines() if not line.startswith('- "'))
    for v in check_output(body, kind="pulse"):
        if v.check != "shape":
            probs.append(f"pulse {v.check}: {v.detail}")
    if find_pii(text):
        probs.append("pulse contains PII")
    return probs
