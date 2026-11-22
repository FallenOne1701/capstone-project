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


# ---- final review fixes: the worker's session is separate from the person's (stale objects) ----

def _other():
    from app import db as dbmod
    return dbmod.SessionLocal()


def _process_in_worker_session(db_session, code, fake_during_translate):
    """Run the desk job in its own session, like the real worker; `fake_during_translate` runs mid-translation."""
    import asyncio

    worker = _other()
    t = worker.query(Ticket).filter_by(code=code).one()

    async def translating(system, user, **kw):
        fake_during_translate()
        return {"text": "हिंदी उत्तर: " + user}

    return worker, t, translating


@pytest.fixture()
def queued(wired, db_session, monkeypatch):
    """A Hinglish ticket made with the AI off (so no translation yet), then re-processed by a separate worker."""
    def make():
        monkeypatch.setattr(get_settings(), "auto_approve", False)
        r = wired.post("/api/ask", json={"text": HINGLISH})
        return r.json()["code"]
    return make


def _worker_translate(monkeypatch, worker, draft_id, during):
    import asyncio

    async def translating(system, user, **kw):
        during()
        return {"text": "हिंदी उत्तर: " + user}

    monkeypatch.setattr(translate, "complete_json", translating)
    d = worker.get(Draft, draft_id)
    held = worker.query(Action).filter_by(draft_id=draft_id).one()   # held, like process_ticket's `a`: goes stale
    assert held.status == "pending" and d.reply
    asyncio.run(ts._add_translation(worker, d))
    worker.commit()


def test_worker_sees_an_approval_made_mid_translation(wired, db_session, queued, monkeypatch):
    code = queued()
    item = _item(wired, code)
    worker = _other()

    def approve_now():
        wired.post(f"/api/desk/actions/{item['action']['id']}/approve", json={"reply": item["draft"]["reply"]})

    _worker_translate(monkeypatch, worker, item["draft"]["id"], approve_now)
    db_session.expire_all()
    assert db_session.query(DraftTranslation).filter_by(draft_id=item["draft"]["id"]).count() == 0
    assert db_session.query(AuditLog).filter_by(verb="translate", entity_id=item["draft"]["id"], detail="late").count() == 1


def test_an_edit_mid_translation_drops_the_old_hindi(wired, db_session, queued, monkeypatch):
    from app.approvals import service as ap
    code = queued()
    item = _item(wired, code)
    worker = _other()
    fixed = ("The exit load of HDFC Mid Cap Fund is 1% if redeemed within 1 year. "
             "Source: https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth Last checked: 2026-11-20.")

    def edit_now():
        person = _other()
        ap.edit_draft(person, item["draft"]["id"], fixed, "page")
        person.close()

    _worker_translate(monkeypatch, worker, item["draft"]["id"], edit_now)
    db_session.expire_all()
    assert db_session.query(DraftTranslation).filter_by(draft_id=item["draft"]["id"]).count() == 0
    assert db_session.query(AuditLog).filter(AuditLog.verb == "translate", AuditLog.entity_id == item["draft"]["id"],
                                             AuditLog.detail.like("discarded:edited%")).count() == 1


def test_a_second_approve_never_strips_approved_hindi(wired, db_session, hindi):
    code = _ask(wired)
    item = _item(wired, code)
    shown = item["draft"]["translation"]["text"]
    url = f"/api/desk/actions/{item['action']['id']}/approve"
    assert wired.post(url, json={"reply": item["draft"]["reply"], "translation": shown}).status_code == 200
    second = wired.post(url, json={"reply": item["draft"]["reply"]})   # a stale card, no Hindi shown
    assert second.status_code == 409
    assert wired.get(f"/api/tickets/{code}").json()["answer_local"]["text"] == shown


def test_hindi_landing_just_before_the_claim_is_not_published(wired, db_session, queued, monkeypatch):
    """The card said "coming…"; the translation lands between the request and the claim: English only."""
    from app.approvals import service as ap
    code = queued()
    item = _item(wired, code)
    real_claim = ap._claim

    def claim_after_hindi_lands(db, action_id, new_status, **kw):
        if new_status == "approved":
            other = _other()
            other.add(DraftTranslation(draft_id=item["draft"]["id"], language="hi", text="हिंदी अनदेखा"))
            other.commit()
            other.close()
        return real_claim(db, action_id, new_status, **kw)

    monkeypatch.setattr(ap, "_claim", claim_after_hindi_lands)
    r = wired.post(f"/api/desk/actions/{item['action']['id']}/approve", json={"reply": item["draft"]["reply"]})
    assert r.status_code == 200
    assert wired.get(f"/api/tickets/{code}").json()["answer_local"] is None


def test_a_failed_save_after_translating_never_fails_the_ticket(wired, db_session, monkeypatch):
    from sqlalchemy.exc import OperationalError

    async def ok(system, user, **kw):
        return {"text": "हिंदी उत्तर: " + user}

    monkeypatch.setattr(translate, "complete_json", ok)
    real_add = ts._add_translation

    async def add_then_lock(db, d):
        await real_add(db, d)
        real_commit = db.commit

        def locked():
            db.commit = real_commit
            raise OperationalError("COMMIT", {}, Exception("database is locked"))
        db.commit = locked

    monkeypatch.setattr(ts, "_add_translation", add_then_lock)
    code = _ask(wired)
    db_session.expire_all()
    t = db_session.query(Ticket).filter_by(code=code).one()
    assert t.status == "in_review"
    assert db_session.query(Draft).filter_by(ticket_id=t.id).count() == 1
    assert db_session.query(Action).filter_by(target_ref=code, status="pending").count() == 1
