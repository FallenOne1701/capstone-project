"""Reviews → ≤5 fixed-vocabulary themes. Keyword rules first; fast LLM only for ambiguous, capped."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.llm.client import complete_json, llm_enabled
from app.models import Review
from app.weekly.vocab import THEME_VOCAB, confident_theme_id, heuristic_theme_id, keyword_scores

_ORDER = list(THEME_VOCAB)
_SYSTEM = (
    "Label each Groww Play Store review with exactly one theme_id from: "
    + ", ".join(f"{k} ({v})" for k, v in THEME_VOCAB.items())
    + ". Mutual fund / SIP / exit load / charges → fees_funding. Generic complaint → app_reliability. "
    "Return JSON {\"labels\": [{\"id\": ..., \"theme_id\": ...}]} covering every id. Never invent ids."
)


@dataclass
class ThemeOut:
    theme_id: str
    label: str
    count: int
    recent_count: int
    review_ids: list[str] = field(default_factory=list)
    window_start: date | None = None
    window_end: date | None = None
    rank: int = 0


async def assign_themes(reviews: list[Review], *, max_llm: int = 48) -> tuple[dict[str, str], int]:
    out: dict[str, str] = {}
    ambiguous: list[Review] = []
    for r in reviews:
        tid = confident_theme_id(r.text_redacted)
        if tid:
            out[r.id] = tid
        else:
            ambiguous.append(r)
    calls = 0
    if llm_enabled():
        budget = ambiguous[:max_llm]
        for i in range(0, len(budget), 12):
            batch = budget[i:i + 12]
            user = "\n".join(f"{r.id} | {r.rating}★ | {r.text_redacted[:300]}" for r in batch)
            data = await complete_json(_SYSTEM, user, fast=True)
            calls += 1
            ids = {r.id for r in batch}
            for item in (data or {}).get("labels", []):
                if item.get("id") in ids and item.get("theme_id") in THEME_VOCAB:
                    out[item["id"]] = item["theme_id"]
    for r in ambiguous:
        # Ties between themes fall back to the heuristic; reviews with no theme signal at all stay unthemed
        # (e.g. "good app") instead of inflating a complaint theme.
        if r.id not in out and max(keyword_scores(r.text_redacted).values()) > 0:
            out[r.id] = heuristic_theme_id(r.text_redacted)
    return out, calls


def build_themes(assign: dict[str, str], reviews: list[Review], *, window_start: date, window_end: date,
                 today: date) -> list[ThemeOut]:
    by_id = {r.id: r for r in reviews}
    recent_start = today - timedelta(days=6)
    groups: dict[str, list[str]] = {}
    for rid, tid in assign.items():
        if rid in by_id:
            groups.setdefault(tid, []).append(rid)
    themes = [ThemeOut(theme_id=tid, label=THEME_VOCAB[tid], count=len(ids),
                       recent_count=sum(1 for i in ids if by_id[i].date >= recent_start),
                       review_ids=sorted(ids), window_start=window_start, window_end=window_end)
              for tid, ids in groups.items() if ids]
    themes.sort(key=lambda t: (-t.count, _ORDER.index(t.theme_id)))
    themes = themes[:5]
    for i, t in enumerate(themes, 1):
        t.rank = i
    return themes
