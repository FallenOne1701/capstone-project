import pytest

from app import deps
from app.models import Action, AuditLog, Draft, Ticket
from tests.conftest_corpus import build_fixture_retriever

H = {"X-Console-Key": "test-pass"}


@pytest.fixture(scope="module")
def fixture_retriever(tmp_path_factory):
    return build_fixture_retriever(tmp_path_factory.mktemp("t"))


@pytest.fixture()
def wired(client, monkeypatch, fixture_retriever):
    monkeypatch.setattr(deps, "get_retriever", lambda: fixture_retriever)
    return client


def test_preview_redacts_and_classifies(wired):
    body = wired.post("/api/ask/preview", json={"text": "exit load of mid cap? my pan ABCDE1234F"}).json()
    assert "ABCDE1234F" not in body["redacted_text"] and body["intent"] == "fee_question"
    assert body["needs_clarification"] is False


def test_preview_ambiguous_asks_clarification(wired):
    body = wired.post("/api/ask/preview", json={"text": "exit load of mid cap and small cap"}).json()
    assert body["needs_clarification"] and len(body["options"]) == 2


@pytest.mark.parametrize("text", ["", "   ", "x" * 501])
def test_ask_rejects_empty_and_long(wired, text):
    assert wired.post("/api/ask", json={"text": text}).status_code == 422


def test_ask_flow_end_to_end(wired, db_session):
    r = wired.post("/api/ask", json={"text": "What is the exit load of HDFC Mid Cap? call 9876543210"})
    assert r.status_code == 200
    code = r.json()["code"]
    t = db_session.query(Ticket).filter_by(code=code).one()
    assert "9876543210" not in t.question_redacted and t.status == "in_review"
    q = wired.get("/api/console/queue", headers=H).json()
    item = next(i for i in q if i["code"] == code)
    assert item["draft"]["citation"].endswith("hdfc-mid-cap-fund-direct-growth")
    aid = item["action"]["id"]
    assert wired.get(f"/api/tickets/{code}").json()["answer"] is None
    assert wired.post(f"/api/console/actions/{aid}/approve", headers=H).status_code == 200
    pub = wired.get(f"/api/tickets/{code}").json()
    assert pub["status"] == "answered" and "Last checked" in pub["answer"]


def test_advice_gets_notice_and_refusal_draft(wired):
    r = wired.post("/api/ask", json={"text": "Should I buy HDFC Defence Fund?"}).json()
    assert r["notice"]
    item = next(i for i in wired.get("/api/console/queue", headers=H).json() if i["code"] == r["code"])
    assert item["draft"]["disposition"] == "refuse"


@pytest.mark.parametrize("text", ["🙂🙂", "एग्जिट लोड क्या है", "asdfghjkl"])
def test_junk_input_never_500(wired, text):
    r = wired.post("/api/ask", json={"text": text})
    assert r.status_code == 200


def test_console_requires_key(wired):
    assert wired.get("/api/console/queue").status_code == 401


def test_unknown_ticket_404(wired):
    assert wired.get("/api/tickets/GRW-NOPE00").status_code == 404


def test_nothing_in_db_contains_raw_pii(wired, db_session):
    wired.post("/api/ask", json={"text": "pan ABCDE1234F acct 50100234567890 phone +91 98765 43210 exit load mid cap"})
    blob = " ".join(str(v) for model in (Ticket, Draft, Action, AuditLog)
                    for row in db_session.query(model) for v in row.__dict__.values())
    for raw in ("ABCDE1234F", "50100234567890", "98765"):
        assert raw not in blob
