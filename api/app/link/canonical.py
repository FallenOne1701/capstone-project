"""Link 2: an approved (canonical) fee explainer answers matching fee questions instead of a fresh draft."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.config import load_schemes
from app.desk.templates import covered_reply
from app.intent.classifier import IntentResult
from app.models import Explainer
from app.weekly.fee_topics import FEE_TOPICS, topic_of


def find_canonical(db: Session, intent: IntentResult, text: str) -> Explainer | None:
    if intent.intent != "fee_question":
        return None
    topic = intent.fact_key if intent.fact_key in FEE_TOPICS else topic_of(text, strict=True)
    if topic is None:
        return None
    return (db.query(Explainer).filter_by(topic=topic, status="canonical")
            .order_by(Explainer.canonical_at.desc(), Explainer.id.desc()).first())


_FIGURE = re.compile(r"\d|₹|%")
# "What is exit load?" / "what does brokerage mean" — a pure definition question keeps the definition alone
_DEFINITION = re.compile(r"(?i)^\s*what\s+(is|are)\s+(an?\s+)?\w+(\s+\w+)?\s*\??\s*$|\bmean(ing|s)?\b|\bdefin")


def _with_figure(bullets: list[dict], first: dict, text: str) -> dict:
    """A concept line with no number ("Groww charges a brokerage fee…") doesn't answer "what does it charge?":
    add the next line from the SAME page that carries the figure. Never borrows from another page."""
    if _FIGURE.search(first["text"]) or _DEFINITION.search(text):
        return first
    start = bullets.index(first) + 1
    extra = next((b for b in bullets[start:] if b["url"] == first["url"] and _FIGURE.search(b["text"])), None)
    if extra is None:
        return first
    return {"text": f"{first['text'].strip().rstrip('.')}. {extra['text'].strip()}", "url": first["url"]}


def reuse_reply(ex: Explainer, intent: IntentResult, text: str = "") -> tuple[str, dict] | None:
    """Scheme asked → that scheme's bullet or None (desk answers it); no scheme → the concept bullet, plus the
    same page's figure line unless the question only asks what the fee is."""
    if not ex.bullets:
        return None
    if len(intent.scheme_ids) == 1:
        url = {s["scheme_id"]: s["url"] for s in load_schemes()["schemes"]}.get(intent.scheme_ids[0])
        bullet = next((b for b in ex.bullets if b["url"] == url), None)
        if bullet is None:
            return None
    elif intent.scheme_ids:
        return None
    else:
        bullet = _with_figure(ex.bullets, ex.bullets[0], text)
    return covered_reply(bullet["text"], bullet["url"], ex.last_checked), bullet
