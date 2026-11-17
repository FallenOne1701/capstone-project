"""Fee explainer: extractive, facts-only bullets from official reference pages + scheme fact sections."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings, is_allowed_source_url
from app.corpus.reference import load_reference, reference_sentences
from app.corpus.refresh import last_checked_for
from app.guard.scope import check_output
from app.models import Ticket
from app.weekly.fee_topics import TOPIC_LABELS

DEFAULT_SCHEMES = ["hdfc-mid-cap-fund-direct-growth", "hdfc-small-cap-fund-direct-growth",
                   "hdfc-large-cap-fund-direct-growth"]
RECIPES: dict[str, list[tuple]] = {
    "exit_load": [("ref", "exit_load", 0), ("ref", "redemption_charges", 0), ("scheme", "exit_load", 3),
                  ("ref", "exit_load", 1)],
    "expense_ratio": [("ref", "expense_ratio", 0), ("ref", "expense_ratio", 1), ("scheme", "expense_ratio", 3)],
    "redemption_charges": [("ref", "redemption_charges", 0), ("ref", "redemption_charges", 1),
                           ("ref", "exit_load", 0), ("scheme", "exit_load", 2)],
    "brokerage": [("ref", "brokerage", 0), ("ref", "brokerage", 1), ("ref", "brokerage", 2),
                  ("ref", "redemption_charges", 0)],
}


@dataclass
class ExplainerDraft:
    topic: str
    title: str
    bullets: list[dict] = field(default_factory=list)
    last_checked: str = ""


def _scheme_fact(scheme_id: str, fact_key: str) -> dict | None:
    p = Path(get_settings().data_processed_dir) / f"{scheme_id}.json"
    if not p.exists():
        return None
    doc = json.loads(p.read_text(encoding="utf-8"))
    for s in doc.get("sections", []):
        if s.get("fact_key") == fact_key:
            return {"text": s["text"].strip().rstrip(".") + ".", "url": doc["source_url"]}
    return None


def _top_schemes(db: Session, n: int) -> list[str]:
    rows = (db.query(Ticket.scheme_id, func.count()).filter(Ticket.intent == "fee_question",
            Ticket.scheme_id.isnot(None)).group_by(Ticket.scheme_id).order_by(func.count().desc()).limit(n).all())
    picked = [r[0] for r in rows]
    return (picked + [s for s in DEFAULT_SCHEMES if s not in picked])[:n]


def build_explainer(db: Session, topic: str, *, schemes: list[str] | None = None) -> ExplainerDraft:
    bullets: list[dict] = []
    for step in RECIPES[topic]:
        if step[0] == "ref":
            sents, doc = reference_sentences(step[1]), load_reference(step[1])
            if doc and len(sents) > step[2]:
                bullets.append({"text": sents[step[2]], "url": doc.url})
        else:
            for sid in (schemes or _top_schemes(db, step[2]))[:step[2]]:
                f = _scheme_fact(sid, step[1])
                if f:
                    bullets.append(f)
    seen, unique = set(), []
    for b in bullets:
        if b["text"] not in seen:
            seen.add(b["text"])
            unique.append(b)
    unique = unique[:6]
    dates = [d for d in (last_checked_for(db, b["url"]) for b in unique) if d]
    return ExplainerDraft(topic=topic, title=f"{TOPIC_LABELS[topic]} — what the official sources say",
                          bullets=unique, last_checked=min(dates) if dates else "")


def validate_explainer(d: ExplainerDraft) -> list[str]:
    probs: list[str] = []
    if not 1 <= len(d.bullets) <= 6:
        probs.append(f"explainer has {len(d.bullets)} bullets (must be 1-6)")
    if len({b.get("url") for b in d.bullets}) < 2:
        probs.append("explainer needs at least 2 distinct official source links")
    if not d.last_checked:
        probs.append("missing last-checked date")
    for i, b in enumerate(d.bullets, 1):
        if not b.get("url") or not is_allowed_source_url(b["url"]):
            probs.append(f"bullet {i} has no allowed source url")
        for v in check_output(b.get("text", ""), kind="reply"):
            if v.check != "shape":
                probs.append(f"bullet {i}: {v.check}")
    return probs


def render_explainer(d: ExplainerDraft) -> str:
    lines = [f"## {d.title}", ""]
    lines += [f"- {b['text']} — Source: {b['url']}" for b in d.bullets]
    lines += ["", f"Last checked: {d.last_checked}"]
    return "\n".join(lines)
