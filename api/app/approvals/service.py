from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.desk.contracts import FactsResult, OrchestratorOutput, RoutingNote
from app.desk.reviewer import review_draft
from app.guard.pii import redact
from app.models import Action, AuditLog, Draft, Ticket


def _now():
    return datetime.now(timezone.utc)


def audit(db: Session, actor: str, verb: str, entity: str, entity_id: int, detail: str = "") -> None:
    db.add(AuditLog(actor=actor, verb=verb, entity=entity, entity_id=entity_id, detail=redact(detail).text))


def _pending(db: Session, action_id: int) -> Action:
    a = db.get(Action, action_id)
    if a is None:
        raise LookupError(f"action {action_id} not found")
    if a.status != "pending":
        raise ValueError(f"action {action_id} is {a.status}, not pending")
    return a


def approve(db: Session, action_id: int, actor: str) -> Action:
    a = _pending(db, action_id)
    if a.type != "reply_publish":
        raise ValueError(f"executor for {a.type} not available")  # Plan 3 adds doc_append/email_draft
    d = db.get(Draft, a.draft_id)
    if d.review_status == "blocked":
        raise ValueError("blocked draft cannot be approved; edit it first")
    t = db.get(Ticket, d.ticket_id)
    now = _now()
    a.status, a.decided_at, a.executed_at = "executed", now, now
    t.status, t.answer_text, t.answered_at = "answered", d.reply, now
    audit(db, actor, "approve", "action", a.id)
    audit(db, actor, "execute", "action", a.id, f"published to ticket {t.code}")
    db.commit()
    return a


def reject(db: Session, action_id: int, actor: str) -> Action:
    a = _pending(db, action_id)
    a.status, a.decided_at = "rejected", _now()
    audit(db, actor, "reject", "action", a.id)
    db.commit()
    return a


def edit_draft(db: Session, draft_id: int, new_reply: str, actor: str) -> Draft:
    d = db.get(Draft, draft_id)
    if d is None:
        raise LookupError(f"draft {draft_id} not found")
    reply = redact(new_reply.strip()).text
    out = OrchestratorOutput(reply=reply, citation=d.citation, last_checked=d.last_checked,
                             disposition=d.disposition, disagreement=d.disposition == "disagree",
                             routing_note=RoutingNote(team=d.routing_team, priority=d.routing_priority, why=d.routing_why))
    facts = (FactsResult(status="covered", scheme_id="edited", fact=reply, citation=d.citation,
                         last_checked=d.last_checked, searched=[]) if d.citation and d.last_checked else None)
    review = review_draft(out, facts=facts, round=1)
    d.reply, d.edited = reply, True
    d.review_status = "pass" if review.status == "pass" else "blocked"
    d.review_failures = [f.model_dump() for f in review.failures]
    audit(db, actor, "edit", "draft", d.id, f"review={d.review_status}")
    db.commit()
    return d
