"""Plan 6 Task 2: drafts reach the Queue before the Hindi translation; Hindi is published only if the approver saw it."""

from datetime import timedelta

import pytest

from app import deps
from app.api.console import _draft_out
from app.config import get_settings
from app.desk import translate
from app.models import Action, AuditLog, Draft, DraftTranslation, Ticket
from app.tickets import service as ts
from tests.conftest_corpus import build_fixture_retriever

HINGLISH = "HDFC mid cap ka exit load kitna hai"


@pytest.fixture(scope="module")
def fixture_retriever(tmp_path_factory):
    return build_fixture_retriever(tmp_path_factory.mktemp("ta"))


@pytest.fixture()
def wired(client, monkeypatch, fixture_retriever):
    monkeypatch.setattr(deps, "get_retriever", lambda: fixture_retriever)
    monkeypatch.setattr(get_settings(), "auto_approve", False)
    return client


def _latest_draft(db):
    return db.query(Draft).order_by(Draft.id.desc()).first()


@pytest.fixture()
def hindi(monkeypatch, db_session):
    """A faithful translator that also records what the Queue showed while it was working."""
    seen = {}

    async def fake(system, user, **kw):
        d = _latest_draft(db_session)
        t = db_session.get(Ticket, d.ticket_id)
        seen["status"] = t.status
        seen["pending"] = _draft_out(d, db_session)["translation_pending"]
        return {"text": "हिंदी उत्तर: " + user}

    monkeypatch.setattr(translate, "complete_json", fake)
    return seen


def _ask(client, text=HINGLISH):
    r = client.post("/api/ask", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()["code"]


def _item(client, code):
    return next(i for i in client.get("/api/desk/queue").json() if i["code"] == code)


def test_ticket_is_in_review_before_translation(wired, db_session, hindi):
    _ask(wired)
    assert hindi["status"] == "in_review"


def test_pending_flag_until_translation_lands(wired, db_session, hindi):
    code = _ask(wired)
    assert hindi["pending"] is True
    draft = _item(wired, code)["draft"]
    assert draft["translation_pending"] is False and "हिंदी" in draft["translation"]["text"]


def test_failed_translation_clears_pending(wired, db_session, monkeypatch):
    async def bad(system, user, **kw):
        return {"text": "no hindi here"}   # fails validation

    monkeypatch.setattr(translate, "complete_json", bad)
    code = _ask(wired)
    item = _item(wired, code)
    assert item["draft"]["translation_pending"] is False and item["draft"]["translation"] is None
    r = wired.post(f"/api/desk/actions/{item['action']['id']}/approve", json={"reply": item["draft"]["reply"]})
    assert r.status_code == 200
    pub = wired.get(f"/api/tickets/{code}").json()
    assert pub["status"] == "answered" and pub["answer_local"] is None


def test_approve_with_seen_hindi_publishes_hindi(wired, db_session, hindi):
    code = _ask(wired)
    item = _item(wired, code)
    shown = item["draft"]["translation"]["text"]
    r = wired.post(f"/api/desk/actions/{item['action']['id']}/approve",
                   json={"reply": item["draft"]["reply"], "translation": shown})
    assert r.status_code == 200
    assert wired.get(f"/api/tickets/{code}").json()["answer_local"]["text"] == shown


def test_approve_without_seen_hindi_gives_english_only(wired, db_session, hindi):
    code = _ask(wired)
    item = _item(wired, code)
    assert item["draft"]["translation"] is not None   # it landed, but this person's card never showed it
    r = wired.post(f"/api/desk/actions/{item['action']['id']}/approve", json={"reply": item["draft"]["reply"]})
    assert r.status_code == 200
    pub = wired.get(f"/api/tickets/{code}").json()
    assert pub["status"] == "answered" and pub["answer_local"] is None
    assert db_session.query(AuditLog).filter_by(verb="discard", entity="translation").count() == 1


def test_translation_after_approval_never_published(wired, db_session, monkeypatch):
    code = _ask(wired)   # LLM off: no translation yet
    item = _item(wired, code)
    wired.post(f"/api/desk/actions/{item['action']['id']}/approve", json={"reply": item["draft"]["reply"]})

    async def late(system, user, **kw):
        return {"text": "हिंदी उत्तर: " + user}

    monkeypatch.setattr(translate, "complete_json", late)
    d = db_session.get(Draft, item["draft"]["id"])
    import asyncio
    asyncio.run(ts._add_translation(db_session, d))
    db_session.commit()
    assert db_session.query(DraftTranslation).filter_by(draft_id=d.id).count() == 0
    assert db_session.query(AuditLog).filter_by(verb="translate", entity_id=d.id, detail="late").count() == 1

    # a row that somehow appears after the decision is still never shown
    a = db_session.query(Action).filter_by(target_ref=code, type="reply_publish").one()
    db_session.add(DraftTranslation(draft_id=d.id, language="hi", text="हिंदी देर से",
                                    created_at=a.decided_at + timedelta(seconds=5)))
    db_session.commit()
    assert wired.get(f"/api/tickets/{code}").json()["answer_local"] is None


def test_auto_mode_translates_before_deciding(wired, db_session, hindi, monkeypatch):
    monkeypatch.setattr(get_settings(), "auto_approve", True)
    code = _ask(wired)
    pub = wired.get(f"/api/tickets/{code}").json()
    assert pub["status"] == "answered" and "हिंदी" in pub["answer_local"]["text"]
