import pytest

from app.approvals.service import approve, edit_draft, reject
from app.models import Action, AuditLog, Draft, Ticket


def _snapshot(db):
    db.expire_all()
    return {m.__tablename__: {r.id: {k: v for k, v in r.__dict__.items() if not k.startswith("_")}
                              for r in db.query(m)} for m in (Ticket, Draft, Action, AuditLog)}


def _diff(a, b):
    changed = {}
    for table in a:
        ids = set(a[table]) | set(b[table])
        changed[table] = sorted(i for i in ids if a[table].get(i) != b[table].get(i))
    return changed


@pytest.fixture()
def two_tickets(db_session):
    rows = []
    for i in range(2):
        t = Ticket(code=f"T{i}", question_redacted="q", status="in_review")
        db_session.add(t); db_session.flush()
        d = Draft(ticket_id=t.id, reply="Fact. Source: https://groww.in/x Last checked: 2026-11-17.", citation="https://groww.in/x",
                  last_checked="2026-11-17", disposition="reply", routing_team="t", routing_priority="P3",
                  routing_why="w", review_status="pass")
        db_session.add(d); db_session.flush()
        a = Action(type="reply_publish", target_label="x", target_ref=t.code, draft_id=d.id)
        db_session.add(a); db_session.flush()
        rows.append((t, d, a))
    db_session.commit()
    return rows


def test_edit_changes_only_that_draft(db_session, two_tickets):
    (t0, d0, a0), _ = two_tickets
    before = _snapshot(db_session)
    edit_draft(db_session, d0.id, "Edited fact. Source: https://groww.in/x Last checked: 2026-11-17.", "agent")
    diff = _diff(before, _snapshot(db_session))
    assert diff["drafts"] == [d0.id] and diff["tickets"] == [] and diff["actions"] == []
    assert len(diff["audit_log"]) == 1


def test_approve_one_does_not_touch_other(db_session, two_tickets):
    (t0, d0, a0), (t1, d1, a1) = two_tickets
    before = _snapshot(db_session)
    approve(db_session, a0.id, "agent")
    diff = _diff(before, _snapshot(db_session))
    assert diff["actions"] == [a0.id] and diff["tickets"] == [t0.id] and diff["drafts"] == []
    assert len(diff["audit_log"]) == 2


def test_reject_leaves_queue_untouched(db_session, two_tickets):
    (t0, d0, a0), _ = two_tickets
    before = _snapshot(db_session)
    reject(db_session, a0.id, "agent")
    diff = _diff(before, _snapshot(db_session))
    assert diff["actions"] == [a0.id] and diff["tickets"] == [t0.id] and diff["drafts"] == []   # its own ticket closes
    assert len(diff["audit_log"]) == 1


def test_cannot_approve_twice_or_blocked(db_session, two_tickets):
    (t0, d0, a0), (t1, d1, a1) = two_tickets
    approve(db_session, a0.id, "agent")
    with pytest.raises(ValueError):
        approve(db_session, a0.id, "agent")
    d1.review_status = "blocked"; db_session.commit()
    with pytest.raises(ValueError):
        approve(db_session, a1.id, "agent")


def test_edit_redacts_pii(db_session, two_tickets):
    (t0, d0, a0), _ = two_tickets
    d = edit_draft(db_session, d0.id, "Call 9876543210. Source: https://groww.in/x Last checked: 2026-11-17.", "agent")
    assert "9876543210" not in d.reply
