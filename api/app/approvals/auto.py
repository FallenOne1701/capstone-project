"""The reviewer agent as approver: publishes passing replies and swaps blocked ones for a fixed safe reply.

Everything still goes through approve()/reject() — claimed, executed and audited — with actor AUTO_ACTOR.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.approvals.service import approve, audit, reject
from app.models import Action, Draft, Ticket

log = logging.getLogger(__name__)
AUTO_ACTOR = "auto-reviewer"


def _latest_draft(db: Session, ticket_id: int) -> Draft | None:
    return db.query(Draft).filter_by(ticket_id=ticket_id).order_by(Draft.id.desc()).first()


def auto_decide(db: Session, ticket_id: int) -> Action | None:
    """Publish the ticket's pending draft if it passed review; otherwise publish the fixed fallback instead."""
    d = _latest_draft(db, ticket_id)
    if d is None:
        return None
    a = db.query(Action).filter_by(type="reply_publish", draft_id=d.id, status="pending").first()
    if a is None:
        return None   # already decided (a second call is a no-op)
    if d.review_status == "pass":
        return approve(db, a.id, AUTO_ACTOR)
    first = (d.review_failures or [{}])[0].get("check", "review")
    reject(db, a.id, AUTO_ACTOR, close_ticket=False)   # the fallback answers it; never show "closed" first
    return publish_fallback(db, ticket_id, first)


def publish_fallback(db: Session, ticket_id: int, reason: str) -> Action:
    """Fixed, LLM-free reply pointing to the official page; reviewed and published like any other reply."""
    from app.desk.contracts import OrchestratorOutput, RoutingNote
    from app.desk.reviewer import review_draft
    from app.desk.templates import fallback_reply
    t = db.get(Ticket, ticket_id)
    reply, url = fallback_reply(t.scheme_id)
    why = f"Fallback: {reason}. Official page: {url}"
    out = OrchestratorOutput(reply=reply, citation=None, last_checked=None, disposition="handoff", disagreement=False,
                             routing_note=RoutingNote(team="Mutual fund support", priority="P2", why=why))
    review = review_draft(out, facts=None, round=1)
    d = Draft(ticket_id=t.id, reply=reply, citation=None, last_checked=None, disposition="fallback",
              routing_team="Mutual fund support", routing_priority="P2", routing_why=why,
              review_status="pass" if review.status == "pass" else "blocked",
              review_failures=[f.model_dump() for f in review.failures], searched=[])
    db.add(d)
    db.flush()
    a = Action(type="reply_publish", target_label=f"Reply to ticket {t.code}", target_ref=t.code, draft_id=d.id,
               source_ref=f"ticket:{t.id}")
    db.add(a)
    db.flush()
    t.status = "in_review"
    audit(db, AUTO_ACTOR, "fallback", "ticket", t.id, f"fallback: {reason}")
    db.commit()
    if d.review_status != "pass":   # a fixed template failing review is a bug: never publish it
        log.error("fallback reply failed review for ticket %s: %s", t.code, d.review_failures)
        t.status = "failed"
        db.commit()
        return a
    return approve(db, a.id, AUTO_ACTOR)


# --- Weekly delivery ---------------------------------------------------------------------------------
DELIVERY_TYPES = ("doc_append", "email_draft")
MAX_DELIVERY_ATTEMPTS = 6


def auto_deliver(db: Session, run_id: int) -> list[Action]:
    """Approve a finished run's Google Doc append, then its Gmail draft (the draft is never sent)."""
    from app.models import WeeklyRun
    run = db.get(WeeklyRun, run_id)
    if run is None or run.status != "awaiting_approval":
        return []
    out = []
    for type_ in DELIVERY_TYPES:   # Doc first: approving it marks the explainer canonical (Link 2)
        a = db.query(Action).filter_by(source_ref=f"weekly_run:{run_id}", type=type_, status="pending").first()
        if a is not None:
            out.append(approve(db, a.id, AUTO_ACTOR))
    return out


def weekly_and_deliver(db: Session, *, now, fetcher=None, run_id: int | None = None):
    """The whole Monday job: build the pulse, then deliver it when auto-approval is on."""
    import asyncio

    from app.config import get_settings
    from app.weekly.run import run_weekly
    kw = {"fetcher": fetcher} if fetcher is not None else {}
    run = asyncio.run(run_weekly(db, now=now, run_id=run_id, **kw))
    if get_settings().auto_approve and run.status == "awaiting_approval":
        auto_deliver(db, run.id)
    return run


def _auto_retries(db: Session, action_id: int) -> int:
    from app.models import AuditLog
    return db.query(AuditLog).filter_by(actor=AUTO_ACTOR, verb="retry", entity="action", entity_id=action_id).count()


def retry_failed_deliveries(db: Session, *, max_attempts: int = MAX_DELIVERY_ATTEMPTS) -> int:
    """Hourly: re-run failed Google writes (usually an expired sign-in), up to max_attempts each. Never replies."""
    from app.approvals.service import retry
    n = 0
    failed = db.query(Action).filter(Action.status == "failed", Action.type.in_(DELIVERY_TYPES)).all()
    for a in failed:
        if _auto_retries(db, a.id) < max_attempts:
            retry(db, a.id, AUTO_ACTOR)
            n += 1
    return n
