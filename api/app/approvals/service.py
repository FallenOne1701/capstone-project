from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.desk.contracts import FactsResult, OrchestratorOutput, RoutingNote
from app.desk.reviewer import review_draft
from app.guard.pii import redact
from app.models import Action, AuditLog, Draft, DraftTranslation, Explainer

MIN_REPLY_CHARS = 10


def _now():
    return datetime.now(timezone.utc)


def audit(db: Session, actor: str, verb: str, entity: str, entity_id: int, detail: str = "") -> None:
    db.add(AuditLog(actor=actor, verb=verb, entity=entity, entity_id=entity_id, detail=redact(detail).text))


def _get(db: Session, action_id: int) -> Action:
    a = db.get(Action, action_id)
    if a is None:
        raise LookupError(f"action {action_id} not found")
    return a


def _claim(db: Session, action_id: int, new_status: str, *, from_status: str = "pending") -> None:
    """Atomically move from_status → new_status in the database; the in-memory object may be stale."""
    res = db.execute(
        update(Action).where(Action.id == action_id, Action.status == from_status)
        .values(status=new_status, decided_at=_now(), error=None),
        execution_options={"synchronize_session": False},
    )
    if res.rowcount != 1:
        db.rollback()
        raise ValueError(f"action {action_id} is no longer {from_status}")


def mark_canonical(db: Session, explainer_id: int) -> Explainer:
    """Make this explainer the one Link 2 reuses — unless a newer weekly run's explainer already is."""
    ex = db.get(Explainer, explainer_id)
    newer = (db.query(Explainer).filter(Explainer.topic == ex.topic, Explainer.status == "canonical",
                                        Explainer.id != ex.id, Explainer.run_id.isnot(None),
                                        Explainer.run_id > (ex.run_id or 0)).first())
    if newer is not None:
        ex.status = "superseded"
        return ex
    for other in db.query(Explainer).filter(Explainer.topic == ex.topic, Explainer.status == "canonical",
                                            Explainer.id != ex.id):
        other.status = "superseded"
    ex.status, ex.canonical_at = "canonical", _now()
    return ex


def _run_explainer(db: Session, a: Action) -> Explainer | None:
    if not a.source_ref.startswith("weekly_run:"):
        return None
    run_id = int(a.source_ref.split(":", 1)[1])
    return db.query(Explainer).filter_by(run_id=run_id).order_by(Explainer.id.desc()).first()


def approve(db: Session, action_id: int, actor: str) -> Action:
    from app.approvals.executors import EXECUTORS
    a = _get(db, action_id)
    if a.type not in EXECUTORS:
        raise ValueError(f"no executor for {a.type}")
    if a.type == "reply_publish" and db.get(Draft, a.draft_id).review_status == "blocked":
        raise ValueError("blocked draft cannot be approved; edit it first")
    _claim(db, action_id, "approved")
    db.refresh(a)
    audit(db, actor, "approve", "action", a.id)
    return _execute(db, a, actor)


def retry(db: Session, action_id: int, actor: str) -> Action:
    """A failed action (e.g. expired Google token) is re-run on an explicit human click — never automatically."""
    a = _get(db, action_id)
    _claim(db, action_id, "approved", from_status="failed")
    db.refresh(a)
    audit(db, actor, "retry", "action", a.id)
    return _execute(db, a, actor)


def _execute(db: Session, a: Action, actor: str) -> Action:
    from app.approvals.executors import EXECUTORS
    db.commit()   # the claim is durable before any external call: no duplicate write on crash, no long DB lock
    try:
        ref = EXECUTORS[a.type](db, a)
    except Exception as exc:  # noqa: BLE001  — no silent retry; the failure is recorded on the action
        a.status, a.error = "failed", redact(f"{type(exc).__name__}: {exc}").text[:500]
        audit(db, actor, "fail", "action", a.id, a.error)
        db.commit()
        return a
    a.status, a.executed_at = "executed", _now()
    audit(db, actor, "execute", "action", a.id, ref)
    if a.type == "doc_append":
        ex = _run_explainer(db, a)
        if ex is not None:
            mark_canonical(db, ex.id)
            audit(db, actor, ex.status, "explainer", ex.id, ex.topic)
    db.commit()
    return a


def reject(db: Session, action_id: int, actor: str) -> Action:
    a = _get(db, action_id)
    _claim(db, action_id, "rejected")
    db.refresh(a)
    audit(db, actor, "reject", "action", a.id)
    if a.type == "doc_append":
        ex = _run_explainer(db, a)
        if ex is not None and ex.status == "draft":
            ex.status = "rejected"
    db.commit()
    return a


def edit_draft(db: Session, draft_id: int, new_reply: str, actor: str) -> Draft:
    d = db.get(Draft, draft_id)
    if d is None:
        raise LookupError(f"draft {draft_id} not found")
    decided = db.query(Action).filter(Action.draft_id == d.id, Action.status != "pending").first()
    if decided is not None:
        raise ValueError(f"draft {draft_id} can't be edited: its action is {decided.status}")
    reply = redact((new_reply or "").strip()).text
    if len(reply) < MIN_REPLY_CHARS:
        raise ValueError("edited reply is empty or too short")
    out = OrchestratorOutput(reply=reply, citation=d.citation, last_checked=d.last_checked,
                             disposition=d.disposition, disagreement=d.disposition == "disagree",
                             routing_note=RoutingNote(team=d.routing_team, priority=d.routing_priority, why=d.routing_why))
    facts = (FactsResult(status="covered", scheme_id="edited", fact=reply, citation=d.citation,
                         last_checked=d.last_checked, searched=[]) if d.citation and d.last_checked else None)
    review = review_draft(out, facts=facts, round=1)
    d.reply, d.edited = reply, True
    # the edited English is what the human approved; an old Hindi version would no longer match it
    db.query(DraftTranslation).filter_by(draft_id=d.id).delete()
    d.review_status = "pass" if review.status == "pass" else "blocked"
    d.review_failures = [f.model_dump() for f in review.failures]
    audit(db, actor, "edit", "draft", d.id, f"review={d.review_status}")
    db.commit()
    return d
