"""Public, read-only views for the single page: this week's pulse and how an answer was checked.

Only public-safe fields leave here: no review ids, recipients, Doc ids, action labels or PII.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import Action, AuditLog, Draft, Explainer, Theme, Ticket, WeeklyRun

_QUOTE = re.compile(r'^- "(.+?)" \((rv_[a-z2-7]+)\)$', re.M)
_AUTH = re.compile(r"(?i)invalid_grant|unauthenticated|unauthorized|\b401\b|token")
AGENTS = ["facts", "pattern", "compliance", "reviewer"]
REVIEW_CHECKS = ["citation", "advice", "performance", "pii", "shape"]
_FALLBACK_WHY = {
    "advice": "The drafted answer read like advice, so a safe reply was sent instead.",
    "performance": "The drafted answer mentioned returns, so a safe reply was sent instead.",
    "pii": "The drafted answer contained personal details, so a safe reply was sent instead.",
    "citation": "The drafted answer's source didn't match, so a safe reply was sent instead.",
    "shape": "The drafted answer was missing its checked date, so a safe reply was sent instead.",
    "desk error": "The system hit an error, so a safe reply was sent instead.",
}
STALE_AFTER_DAYS = 7


def _delivery_word(db: Session, a: Action | None) -> str:
    from app.approvals.auto import AUTO_ACTOR, MAX_DELIVERY_ATTEMPTS
    if a is None or a.status == "pending":
        return "not started"
    if a.status == "executed":
        return "delivered"
    if a.status == "rejected":
        return "not sent"
    if a.status == "approved":
        return "in progress"
    tries = db.query(AuditLog).filter_by(actor=AUTO_ACTOR, verb="retry", entity="action", entity_id=a.id).count()
    if tries < MAX_DELIVERY_ATTEMPTS:
        return "pending (retrying)"
    return "failed — sign-in expired" if _AUTH.search(a.error or "") else "failed"


def build_summary(db: Session, today: date) -> dict | None:
    run = (db.query(WeeklyRun).filter(WeeklyRun.status.notin_(("failed", "running")))
           .order_by(WeeklyRun.id.desc()).first())
    if run is None:
        return None
    themes = db.query(Theme).filter_by(run_id=run.id).order_by(Theme.rank).all()
    theme_of = {rid: t.label for t in themes for rid in t.review_ids}
    quotes = [{"text": text, "theme": theme_of.get(rid)} for text, rid in _QUOTE.findall(run.pulse_text or "")]
    ex = db.query(Explainer).filter_by(run_id=run.id).first()
    if ex is not None:   # the current canonical one for the topic, if a newer run superseded this
        ex = (db.query(Explainer).filter_by(topic=ex.topic, status="canonical").order_by(Explainer.id.desc()).first()
              or ex)
    acts = {a.type: a for a in db.query(Action).filter_by(source_ref=f"weekly_run:{run.id}")}
    from app.config import get_settings
    from app.link.question_keys import repeated_questions
    s = get_settings()
    rep = repeated_questions(db, now=datetime.now(timezone.utc), threshold=s.repeat_threshold, days=s.repeat_days)
    return {
        "week_ending": run.window_end.isoformat() if run.window_end else None,
        "window_start": run.window_start.isoformat() if run.window_start else None,
        "window_end": run.window_end.isoformat() if run.window_end else None,
        "stale": bool(run.window_end and today - run.window_end > timedelta(days=STALE_AFTER_DAYS)),
        "review_count": run.review_count,
        "themes": [{"label": t.label, "count": t.count, "recent_count": t.recent_count} for t in themes[:3]],
        "quotes": quotes,
        "repeated": [{"label": r.label, "count": r.count} for r in rep],
        "explainer": {"title": ex.title, "bullets": [{"text": b["text"], "url": b["url"]} for b in ex.bullets],
                      "last_checked": ex.last_checked} if ex else None,
        "delivery": {"doc": _delivery_word(db, acts.get("doc_append")),
                     "email_draft": _delivery_word(db, acts.get("email_draft"))},
    }


def ticket_checks(db: Session, t: Ticket) -> dict | None:
    """How the published answer was checked — from the draft whose reply_publish actually executed."""
    if t.status != "answered":
        return None
    a = (db.query(Action).filter_by(type="reply_publish", status="executed", target_ref=t.code)
         .order_by(Action.id.desc()).first())
    d = db.get(Draft, a.draft_id) if a else None
    if d is None:
        return None
    fallback = None
    if d.disposition == "fallback":
        reason = (d.routing_why or "").removeprefix("Fallback: ").split(".")[0].strip()
        fallback = _FALLBACK_WHY.get(reason, "A safe reply was sent instead of an unchecked answer.")
    return {"agents": ["reviewer"] if fallback else AGENTS, "review": d.review_status, "checks": REVIEW_CHECKS,
            "citation": d.citation, "last_checked": d.last_checked, "reused_explainer": d.reused_explainer_id,
            "fallback": fallback}
