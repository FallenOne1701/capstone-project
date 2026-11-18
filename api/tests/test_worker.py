"""Background ticket processing, startup recovery and console re-run (Plan 3 Task 3)."""

import pytest

from app import deps
from app.config import get_settings
from app.models import AuditLog, Draft, Ticket
from app.tickets import worker
from tests.conftest_corpus import build_fixture_retriever

H = {"X-Console-Key": "test-pass"}


@pytest.fixture(scope="module")
def fixture_retriever(tmp_path_factory):
    return build_fixture_retriever(tmp_path_factory.mktemp("w"))


@pytest.fixture()
def wired(client, monkeypatch, fixture_retriever):
    monkeypatch.setattr(deps, "get_retriever", lambda: fixture_retriever)
    return client


def _ticket(db, code="GRW-TEST01", status="received"):
    t = Ticket(code=code, channel="text", language="en", question_redacted="exit load of HDFC mid cap",
               pii_types=[], intent="fee_question", status=status)
    db.add(t)
    db.commit()
    return t


def test_ask_returns_before_processing(wired, db_session, monkeypatch):
    monkeypatch.setattr(get_settings(), "ticket_worker_inline", False)
    sent = []
    monkeypatch.setattr(worker, "submit", sent.append)
    r = wired.post("/api/ask", json={"text": "exit load of HDFC mid cap"})
    assert r.status_code == 200 and r.json()["status"] == "received"
    t = db_session.query(Ticket).filter_by(code=r.json()["code"]).one()
    assert sent == [t.id]
    assert db_session.query(Draft).filter_by(ticket_id=t.id).count() == 0


def test_recover_resubmits_received_tickets(db_session, monkeypatch):
    a = _ticket(db_session, "GRW-AAAAA1", "received")
    _ticket(db_session, "GRW-AAAAA2", "in_review")
    sent = []
    monkeypatch.setattr(worker, "submit", sent.append)
    assert worker.recover(db_session) == [a.id]
    assert sent == [a.id]


def test_reprocess_failed_ticket(wired, db_session, monkeypatch):
    t = _ticket(db_session, status="failed")
    sent = []
    monkeypatch.setattr(worker, "submit", sent.append)
    r = wired.post(f"/api/console/tickets/{t.code}/reprocess", headers=H)
    assert r.status_code == 200 and r.json() == {"code": t.code, "status": "received"}
    db_session.refresh(t)
    assert t.status == "received" and sent == [t.id]
    assert db_session.query(AuditLog).filter_by(verb="reprocess", entity_id=t.id).count() == 1


def test_reprocess_rejects_answered(wired, db_session):
    t = _ticket(db_session, status="answered")
    assert wired.post(f"/api/console/tickets/{t.code}/reprocess", headers=H).status_code == 409


def test_reprocess_unknown_ticket_404(wired):
    assert wired.post("/api/console/tickets/GRW-NOPE00/reprocess", headers=H).status_code == 404


def test_reprocess_needs_console_key(wired, db_session):
    t = _ticket(db_session, status="failed")
    assert wired.post(f"/api/console/tickets/{t.code}/reprocess").status_code == 401


def test_worker_job_uses_its_own_session(db_session, monkeypatch, fixture_retriever):
    monkeypatch.setattr(deps, "get_retriever", lambda: fixture_retriever)
    t = _ticket(db_session)
    worker._job(t.id)
    db_session.expire_all()
    assert db_session.get(Ticket, t.id).status == "in_review"
    assert db_session.query(Draft).filter_by(ticket_id=t.id).count() == 1


def test_worker_job_skips_ticket_already_processed(db_session, monkeypatch, fixture_retriever):
    monkeypatch.setattr(deps, "get_retriever", lambda: fixture_retriever)
    t = _ticket(db_session)
    worker._job(t.id)
    worker._job(t.id)   # a duplicate submit (recover + reprocess) must not create a second draft
    assert db_session.query(Draft).filter_by(ticket_id=t.id).count() == 1
