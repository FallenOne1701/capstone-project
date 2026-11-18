"""Validated Hindi replies, approved together with the English draft (Plan 3 Task 4)."""

import pytest

from app import deps
from app.approvals import service as ap
from app.desk import translate
from app.desk.translate import validate_translation
from app.models import AuditLog, Draft, DraftTranslation, Ticket
from tests.conftest_corpus import build_fixture_retriever

H = {"X-Console-Key": "test-pass"}
HINGLISH = "HDFC mid cap ka exit load kitna hai"
SRC = ("The exit load of HDFC Mid Cap Fund is 1% if redeemed within 1 year. "
       "Source: https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth Last checked: 2026-11-17")


@pytest.fixture(scope="module")
def fixture_retriever(tmp_path_factory):
    return build_fixture_retriever(tmp_path_factory.mktemp("tr"))


@pytest.fixture()
def wired(client, monkeypatch, fixture_retriever):
    monkeypatch.setattr(deps, "get_retriever", lambda: fixture_retriever)
    return client


@pytest.fixture()
def hindi_llm(monkeypatch):
    """A translator that keeps every URL and number — what a faithful translation looks like to the validator."""
    calls = []

    async def fake(system, user, **kw):
        calls.append(user)
        return {"text": "हिंदी उत्तर: " + user}

    monkeypatch.setattr(translate, "complete_json", fake)
    return calls


def _ask(client, text):
    r = client.post("/api/ask", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()["code"]


def _draft(db, code):
    t = db.query(Ticket).filter_by(code=code).one()
    return t, db.query(Draft).filter_by(ticket_id=t.id).one()


def test_hindi_question_gets_hindi_translation_stored(wired, db_session, hindi_llm):
    t, d = _draft(db_session, _ask(wired, HINGLISH))
    assert t.language == "hinglish" and d.review_status == "pass"
    tr = db_session.query(DraftTranslation).filter_by(draft_id=d.id).one()
    assert tr.language == "hi" and "हिंदी" in tr.text
    assert db_session.query(AuditLog).filter_by(verb="translate", entity_id=d.id, detail="ok").count() == 1


def test_translation_that_changes_numbers_or_links_is_discarded():
    url = "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth"
    good = f"एग्जिट लोड 1% है, 1 वर्ष के भीतर। Source: {url} Last checked: 2026-11-17"
    assert validate_translation(SRC, good) == []
    assert validate_translation(SRC, good.replace("1%", "2%"))            # a changed number
    assert validate_translation(SRC, good.replace(url, ""))               # a dropped link
    assert validate_translation(SRC, good + " https://groww.in/other")    # an extra link
    assert validate_translation(SRC, SRC)                                 # no Devanagari at all
    assert validate_translation(SRC, good + " PAN ABCDE1234F")            # PII introduced
    assert validate_translation(SRC, good * 4)                            # runaway length


def test_bad_translation_is_not_stored(wired, db_session, monkeypatch):
    async def fake(system, user, **kw):
        return {"text": "एग्जिट लोड 2% है"}   # wrong number, link dropped
    monkeypatch.setattr(translate, "complete_json", fake)
    _, d = _draft(db_session, _ask(wired, HINGLISH))
    assert db_session.query(DraftTranslation).filter_by(draft_id=d.id).count() == 0
    log = db_session.query(AuditLog).filter_by(verb="translate", entity_id=d.id).one()
    assert log.detail.startswith("discarded:")


def test_english_question_not_translated(wired, db_session, hindi_llm):
    _, d = _draft(db_session, _ask(wired, "What is the exit load of HDFC Mid Cap Fund?"))
    assert hindi_llm == []
    assert db_session.query(DraftTranslation).count() == 0


def test_blocked_draft_not_translated(wired, db_session, hindi_llm, monkeypatch):
    from app.desk.contracts import ReviewerResult
    from app.tickets import service as ts
    from app.desk.orchestrator import run_desk
    monkeypatch.setattr(ts, "find_canonical", lambda *a, **k: None)

    async def blocked_desk(*a, **k):
        res = await run_desk(*a, **k)
        return res.model_copy(update={"review": ReviewerResult(status="blocked", round=2, failures=[])})
    monkeypatch.setattr(ts, "run_desk", blocked_desk)
    _, d = _draft(db_session, _ask(wired, HINGLISH))
    assert d.review_status == "blocked"
    assert hindi_llm == []


def test_edit_drops_translation(wired, db_session, hindi_llm):
    _, d = _draft(db_session, _ask(wired, HINGLISH))
    assert db_session.query(DraftTranslation).filter_by(draft_id=d.id).count() == 1
    ap.edit_draft(db_session, d.id, SRC, "console")
    assert db_session.query(DraftTranslation).filter_by(draft_id=d.id).count() == 0
    item = next(i for i in wired.get("/api/console/queue", headers=H).json() if i["draft"]["id"] == d.id)
    assert item["draft"]["translation"] is None


def test_console_queue_shows_translation(wired, db_session, hindi_llm):
    code = _ask(wired, HINGLISH)
    item = next(i for i in wired.get("/api/console/queue", headers=H).json() if i["code"] == code)
    assert item["draft"]["translation"]["language"] == "hi"
    assert "हिंदी" in item["draft"]["translation"]["text"]


def test_public_ticket_shows_hindi_only_after_approval(wired, db_session, hindi_llm):
    code = _ask(wired, HINGLISH)
    assert wired.get(f"/api/tickets/{code}").json()["answer_local"] is None
    item = next(i for i in wired.get("/api/console/queue", headers=H).json() if i["code"] == code)
    assert wired.post(f"/api/console/actions/{item['action']['id']}/approve", headers=H).status_code == 200
    pub = wired.get(f"/api/tickets/{code}").json()
    assert pub["answer_local"]["language"] == "hi" and "हिंदी" in pub["answer_local"]["text"]
    assert "Last checked" in pub["answer"]


def test_llm_off_publishes_english(wired, db_session):
    code = _ask(wired, HINGLISH)
    item = next(i for i in wired.get("/api/console/queue", headers=H).json() if i["code"] == code)
    wired.post(f"/api/console/actions/{item['action']['id']}/approve", headers=H)
    pub = wired.get(f"/api/tickets/{code}").json()
    assert pub["status"] == "answered" and pub["answer_local"] is None and pub["answer"]
