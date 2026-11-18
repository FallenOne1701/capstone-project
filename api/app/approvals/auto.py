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
    reject(db, a.id, AUTO_ACTOR)
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
