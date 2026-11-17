"""Link 2: an approved (canonical) fee explainer answers matching fee questions instead of a fresh draft."""

from __future__ import annotations

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


def reuse_reply(ex: Explainer, intent: IntentResult) -> tuple[str, dict] | None:
    """Scheme asked → that scheme's bullet or None (desk answers it); no scheme → the concept bullet."""
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
        bullet = ex.bullets[0]
    return covered_reply(bullet["text"], bullet["url"], ex.last_checked), bullet
