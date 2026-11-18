"""Clarification answer and voice channel on /api/ask (Plan 3 Task 2)."""

import pytest

from app import deps
from app.models import Draft, Ticket
from tests.conftest_corpus import build_fixture_retriever

MID = "hdfc-mid-cap-fund-direct-growth"


@pytest.fixture(scope="module")
def fixture_retriever(tmp_path_factory):
    return build_fixture_retriever(tmp_path_factory.mktemp("c"))


@pytest.fixture()
def wired(client, monkeypatch, fixture_retriever):
    monkeypatch.setattr(deps, "get_retriever", lambda: fixture_retriever)
    return client


def _ticket(db, code):
    return db.query(Ticket).filter_by(code=code).one()


def test_clarified_scheme_is_answered(wired, db_session):
    r = wired.post("/api/ask", json={"text": "exit load of HDFC mid cap and small cap", "scheme_id": MID})
    assert r.status_code == 200, r.text
    t = _ticket(db_session, r.json()["code"])
    assert t.scheme_id == MID
    d = db_session.query(Draft).filter_by(ticket_id=t.id).one()
    assert d.citation.endswith(MID)


def test_scheme_id_not_in_question_is_ignored(wired, db_session):
    r = wired.post("/api/ask", json={"text": "exit load of HDFC mid cap and small cap",
                                     "scheme_id": "hdfc-gilt-fund-direct-growth"})
    assert r.status_code == 200
    assert _ticket(db_session, r.json()["code"]).scheme_id is None


def test_voice_channel_recorded(wired, db_session):
    r = wired.post("/api/ask", json={"text": "exit load of HDFC mid cap", "channel": "voice"})
    assert _ticket(db_session, r.json()["code"]).channel == "voice"


def test_unknown_channel_rejected(wired):
    assert wired.post("/api/ask", json={"text": "exit load of HDFC mid cap", "channel": "fax"}).status_code == 422
