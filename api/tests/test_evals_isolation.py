"""Plan 4b Task 2: the edit-isolation eval."""

from app.db import Base
from app.evals.isolation import run_isolation
from app.evals.snapshot import snapshot


def test_snapshot_covers_every_table(db_session):
    from app import models  # noqa: F401
    assert set(snapshot(db_session)) == {t.name for t in Base.metadata.sorted_tables}


def test_isolation_suite_passes_on_current_code(db_session):
    r = run_isolation(db_session)
    assert r.total == 5
    assert r.passed == 5, [(c.case_id, c.detail) for c in r.cases if not c.passed]


def test_isolation_catches_a_stray_write(db_session, monkeypatch):
    from app.approvals import service
    from app.evals import isolation
    from app.models import Ticket
    real = service.approve

    def leaky(db, action_id, actor):
        a = real(db, action_id, actor)
        other = db.query(Ticket).filter(Ticket.code == isolation.OTHER_CODE).one()
        other.answer_text = "touched"
        db.commit()
        return a
    monkeypatch.setattr(isolation, "approve", leaky)
    r = run_isolation(db_session)
    bad = {c.case_id: c.detail for c in r.cases if not c.passed}
    assert "approve_reply" in bad and "tickets" in bad["approve_reply"]


def test_isolation_never_calls_google(db_session, monkeypatch):
    from app.approvals import executors
    called = []
    monkeypatch.setitem(executors.EXECUTORS, "doc_append", lambda db, a: called.append(a.id) or "real")
    run_isolation(db_session)
    assert called == []   # the suite swaps in its own stub for the duration of the doc approve
    assert executors.EXECUTORS["doc_append"] is not None
