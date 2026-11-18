"""The reviewer agent approves passing replies; blocked drafts get a fixed fallback (Plan 3b Task 1)."""

import pytest

from app import deps
from app.approvals import auto
from app.config import get_settings
from app.desk.contracts import ReviewerResult
from app.desk.templates import ADVICE_REFUSAL
from app.models import Action, AuditLog, Draft, DraftTranslation, Ticket
from app.tickets import service as ts, worker
from tests.conftest_corpus import build_fixture_retriever

MID_URL = "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth"


@pytest.fixture(scope="module")
def fixture_retriever(tmp_path_factory):
    return build_fixture_retriever(tmp_path_factory.mktemp("auto"))


@pytest.fixture()
def wired(client, monkeypatch, fixture_retriever):
    monkeypatch.setattr(deps, "get_retriever", lambda: fixture_retriever)
    return client


@pytest.fixture()
def auto_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "auto_approve", True)


@pytest.fixture()
def blocked_desk(monkeypatch):
    from app.desk.orchestrator import run_desk
    monkeypatch.setattr(ts, "find_canonical", lambda *a, **k: None)

    async def desk(*a, **k):
        res = await run_desk(*a, **k)
        return res.model_copy(update={"review": ReviewerResult(status="blocked", round=2, failures=[
            {"check": "advice", "detail": "advice wording"}])})
    monkeypatch.setattr(ts, "run_desk", desk)


def _ask(client, text):
    r = client.post("/api/ask", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()["code"]


def _ticket(db, code):
    db.expire_all()
    return db.query(Ticket).filter_by(code=code).one()


def test_passing_draft_is_published_automatically(wired, db_session, auto_on):
    t = _ticket(db_session, _ask(wired, "What is the exit load of HDFC Mid Cap Fund?"))
    assert t.status == "answered" and MID_URL in t.answer_text
    a = db_session.query(Action).filter_by(type="reply_publish", target_ref=t.code).one()
    assert a.status == "executed"
    assert db_session.query(AuditLog).filter_by(actor=auto.AUTO_ACTOR, verb="approve", entity_id=a.id).count() == 1


def test_blocked_draft_gets_fallback_not_published(wired, db_session, auto_on, blocked_desk):
    t = _ticket(db_session, _ask(wired, "What is the exit load of HDFC Mid Cap Fund?"))
    assert t.status == "answered"
    assert t.answer_text.startswith("We couldn't confirm an answer to this from official sources.")
    assert "official HDFC Mid Cap page on Groww" in t.answer_text and "http" not in t.answer_text
    drafts = db_session.query(Draft).filter_by(ticket_id=t.id).order_by(Draft.id).all()
    assert [d.disposition for d in drafts][-1] == "fallback"
    acts = {a.draft_id: a.status for a in db_session.query(Action).filter_by(type="reply_publish", target_ref=t.code)}
    assert acts[drafts[0].id] == "rejected" and acts[drafts[-1].id] == "executed"
    assert "Fallback: advice" in drafts[-1].routing_why


def test_fallback_publishes_no_hindi_from_blocked_draft(wired, db_session, blocked_desk, monkeypatch):
    code = _ask(wired, "HDFC mid cap ka exit load kitna hai")      # auto off: stays pending
    t = _ticket(db_session, code)
    blocked = db_session.query(Draft).filter_by(ticket_id=t.id).one()
    db_session.add(DraftTranslation(draft_id=blocked.id, language="hi", text="हिंदी 1% https://x"))
    db_session.commit()
    monkeypatch.setattr(get_settings(), "auto_approve", True)
    auto.auto_decide(db_session, t.id)
    pub = wired.get(f"/api/tickets/{code}").json()
    assert pub["status"] == "answered" and pub["answer_local"] is None


def test_auto_decide_is_idempotent(wired, db_session, auto_on):
    t = _ticket(db_session, _ask(wired, "What is the exit load of HDFC Mid Cap Fund?"))
    assert auto.auto_decide(db_session, t.id) is None          # already published: nothing pending
    assert db_session.query(AuditLog).filter_by(actor=auto.AUTO_ACTOR, verb="approve").count() == 1
    assert db_session.query(Action).filter_by(status="executed", target_ref=t.code).count() == 1


def test_desk_crash_retried_once_then_fallback(db_session, auto_on, monkeypatch, fixture_retriever):
    import asyncio
    monkeypatch.setattr(deps, "get_retriever", lambda: fixture_retriever)
    calls = []

    async def boom(*a, **k):
        calls.append(1)
        raise RuntimeError("desk down")
    monkeypatch.setattr(ts, "run_desk", boom)
    monkeypatch.setattr(ts, "find_canonical", lambda *a, **k: None)
    monkeypatch.setattr(get_settings(), "auto_approve", False)   # create only
    t, _ = asyncio.run(ts.create_ticket(db_session, "What is the exit load of HDFC Mid Cap Fund?"))
    monkeypatch.setattr(get_settings(), "auto_approve", True)
    worker._job(t.id)
    t = _ticket(db_session, t.code)
    assert len(calls) == 2
    assert t.status == "answered" and t.answer_text.startswith("We couldn't confirm an answer")
    assert db_session.query(AuditLog).filter(AuditLog.detail.like("fallback: desk error%")).count() == 1


def test_auto_approve_off_keeps_pending(wired, db_session):
    t = _ticket(db_session, _ask(wired, "What is the exit load of HDFC Mid Cap Fund?"))
    assert t.status == "in_review"
    assert db_session.query(Action).filter_by(target_ref=t.code).one().status == "pending"


def test_refusal_is_published_automatically(wired, db_session, auto_on):
    t = _ticket(db_session, _ask(wired, "Should I buy HDFC Defence Fund?"))
    assert t.status == "answered" and t.answer_text == ADVICE_REFUSAL
