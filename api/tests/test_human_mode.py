"""Plan 3c Task 1: a person approves by default; rejecting a reply closes the ticket."""

from app.approvals.service import reject
from app.config import Settings, get_settings
from app.models import Action, AuditLog, Draft, Ticket


def _ticket(db, code="GRW-HUMAN1", status="in_review", review="pass"):
    t = Ticket(code=code, channel="text", language="en", question_redacted="q", pii_types=[],
               intent="fee_question", status=status)
    db.add(t)
    db.flush()
    d = Draft(ticket_id=t.id, reply="r", disposition="reply", routing_team="x", routing_priority="P3",
              routing_why="y", review_status=review)
    db.add(d)
    db.flush()
    a = Action(type="reply_publish", target_label=f"Reply to ticket {code}", target_ref=code, draft_id=d.id)
    db.add(a)
    db.commit()
    return t, a


def test_auto_approve_defaults_off(monkeypatch):
    monkeypatch.delenv("AUTO_APPROVE", raising=False)
    assert Settings(_env_file=None).auto_approve is False


def test_reject_reply_closes_ticket(db_session):
    t, a = _ticket(db_session)
    reject(db_session, a.id, "page")
    db_session.refresh(t)
    db_session.refresh(a)
    assert t.status == "closed"
    assert a.status == "rejected"
    rows = db_session.query(AuditLog).filter_by(actor="page", verb="reject", entity_id=a.id).all()
    assert len(rows) == 1


def test_reject_never_reopens_answered_ticket(db_session):
    t, a = _ticket(db_session, status="answered")
    reject(db_session, a.id, "page")
    db_session.refresh(t)
    assert t.status == "answered"


def test_retry_job_idle_in_human_mode(db_session, monkeypatch):
    from app import scheduler
    monkeypatch.setattr(get_settings(), "auto_approve", False)
    a = Action(type="doc_append", target_label="Doc", target_ref="doc", content="x", source_ref="weekly_run:1",
               status="failed", error="expired")
    db_session.add(a)
    db_session.commit()
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    scheduler._delivery_retry_job()
    db_session.refresh(a)
    assert a.status == "failed"
    assert db_session.query(AuditLog).filter_by(verb="retry", entity_id=a.id).count() == 0


def test_ticket_view_says_who_approves(client, db_session, monkeypatch):
    _ticket(db_session, code="GRW-HUMAN2")
    assert client.get("/api/tickets/GRW-HUMAN2").json()["approval"] == "person"
    monkeypatch.setattr(get_settings(), "auto_approve", True)
    assert client.get("/api/tickets/GRW-HUMAN2").json()["approval"] == "auto"
