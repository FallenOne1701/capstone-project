"""Regression tests for the final-review findings (C1–C3, I1–I7)."""

import asyncio
import logging

import pytest
from sqlalchemy import update

from app.approvals.service import approve, edit_draft, reject
from app.corpus.query_parser import detect_fact_key
from app.desk.contracts import FactsResult, OrchestratorOutput, RoutingNote
from app.desk.facts import run_facts
from app.desk.reviewer import review_draft
from app.guard.logfilter import RedactingFilter
from app.guard.pii import redact
from app.guard.scope import detect_performance
from app.intent.classifier import classify_intent
from app.models import Action, Draft, Ticket
from tests.conftest_corpus import build_fixture_retriever


# --- C1: fact phrases must match whole words -------------------------------------------------
@pytest.mark.parametrize("query,expected", [
    ("What is the riskometer level of HDFC Gilt fund?", "riskometer"),
    ("lock-in period of HDFC ELSS after I invest", "lock_in"),
    ("exit load of HDFC ultra short to short term fund", "exit_load"),
    ("objective of HDFC medium to long term fund", "investment_objective"),
    ("How do I stop my SIP in HDFC mid cap?", None),
    ("better fund than mid cap?", None),
    ("TER of HDFC mid cap", "expense_ratio"),
    ("minimum sip of hdfc mid cap", "min_sip"),
])
def test_fact_key_whole_word(query, expected):
    assert detect_fact_key(query) == expected


# --- C2: scheme-only questions must not get an unrelated fact --------------------------------
@pytest.fixture(scope="module")
def retriever(tmp_path_factory):
    return build_fixture_retriever(tmp_path_factory.mktemp("rf"))


@pytest.mark.parametrize("q", [
    "AUM of HDFC mid cap", "NAV of HDFC mid cap", "fund manager of HDFC large cap",
    "stamp duty on HDFC mid cap", "How do I redeem my HDFC small cap units?",
])
def test_scheme_without_known_fact_is_not_covered(retriever, q):
    f = run_facts(q, retriever, lambda u: "2026-11-17")
    assert f.status == "not_covered" and f.searched


def test_term_schemes_answer_the_asked_fact(retriever):
    f = run_facts("exit load of HDFC ultra short to short term fund", retriever, lambda u: "2026-11-17")
    assert f.status == "covered" and "exit load" in f.fact.lower()


# --- C3: mixed-spacing PAN ------------------------------------------------------------------
@pytest.mark.parametrize("raw", ["my pan ABCDE 1234F", "pan ABCDE1234 F", "pan A B C D E 1234 F", "pan abcd e1234f"])
def test_mixed_spacing_pan_redacted(raw):
    r = redact(raw)
    assert "PAN" in r.pii_types and "1234" not in r.text


def test_sip_sentence_still_not_pan():
    assert redact("Minimum SIP is 1000 a month.").pii_types == []


# --- I1: covered reply must carry its citation in the text; empty edits rejected ------------
URL = "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth"


def _out(reply, disposition="reply"):
    return OrchestratorOutput(reply=reply, citation=URL if disposition == "reply" else None,
                              last_checked="2026-11-17" if disposition == "reply" else None,
                              disposition=disposition, disagreement=False,
                              routing_note=RoutingNote(team="t", priority="P3", why="w"))


def test_covered_reply_without_link_fails():
    assert "citation" in {f.check for f in review_draft(_out("Exit load is 1%. Last checked: 2026-11-17."), facts=None, round=1).failures}


@pytest.fixture()
def one(db_session):
    t = Ticket(code="T9", question_redacted="q", status="in_review")
    db_session.add(t); db_session.flush()
    d = Draft(ticket_id=t.id, reply=f"Fact. Source: {URL} Last checked: 2026-11-17.", citation=URL,
              last_checked="2026-11-17", disposition="reply", routing_team="t", routing_priority="P3",
              routing_why="w", review_status="pass")
    db_session.add(d); db_session.flush()
    a = Action(type="reply_publish", target_label="x", target_ref=t.code, draft_id=d.id)
    db_session.add(a); db_session.commit()
    return t, d, a


@pytest.mark.parametrize("text", ["", "   ", "ok"])
def test_empty_edit_rejected(db_session, one, text):
    with pytest.raises(ValueError):
        edit_draft(db_session, one[1].id, text, "agent")


# --- I2: approve claims the action atomically ------------------------------------------------
def test_approve_uses_db_state_not_stale_object(db_session, one):
    t, d, a = one
    db_session.get(Action, a.id)  # load into identity map as pending
    db_session.execute(update(Action).where(Action.id == a.id).values(status="executed"),
                       execution_options={"synchronize_session": False})
    with pytest.raises(ValueError):
        approve(db_session, a.id, "agent")


def test_reject_uses_db_state_not_stale_object(db_session, one):
    t, d, a = one
    db_session.get(Action, a.id)
    db_session.execute(update(Action).where(Action.id == a.id).values(status="executed"),
                       execution_options={"synchronize_session": False})
    with pytest.raises(ValueError):
        reject(db_session, a.id, "agent")


# --- I3: no edits after the action is decided -------------------------------------------------
def test_edit_after_approve_rejected(db_session, one):
    t, d, a = one
    approve(db_session, a.id, "agent")
    with pytest.raises(ValueError):
        edit_draft(db_session, d.id, f"Other fact. Source: {URL} Last checked: 2026-11-17.", "agent")


# --- I4: console auth -------------------------------------------------------------------------
@pytest.mark.parametrize("pw", ["", "change-me"])
def test_console_unconfigured_password_refused(client, monkeypatch, pw):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "console_password", pw)
    assert client.get("/api/console/queue", headers={"X-Console-Key": pw}).status_code == 503


# --- I5: tracebacks and non-str args are redacted --------------------------------------------
def test_exception_traceback_redacted(caplog):
    lg = logging.getLogger("t.exc")
    lg.addFilter(RedactingFilter())
    with caplog.at_level(logging.INFO, logger="t.exc"):
        try:
            raise ValueError("pan ABCDE1234F phone 9876543210")
        except ValueError as exc:
            lg.exception("failed")
            lg.warning("got %s", exc)
    assert "ABCDE1234F" not in caplog.text and "9876543210" not in caplog.text


# --- I6: official objective wording is not a performance claim -------------------------------
def test_objective_returns_wording_allowed():
    assert not detect_performance("The scheme seeks to generate reasonable returns with investments in government securities.")


@pytest.mark.parametrize("text", ["Expected returns are high.", "The fund gave 24% returns last year.", "Returns of 18% in 2025."])
def test_return_claims_still_flagged(text):
    assert detect_performance(text)


# --- I7: transactional how-to is not advice ---------------------------------------------------
@pytest.mark.parametrize("q", ["What is the process to sell my HDFC mid cap units?",
                               "Can I switch from regular to direct in HDFC mid cap?"])
def test_transactional_howto_not_advice(q):
    assert asyncio.run(classify_intent(q)).intent == "how_to_process"
