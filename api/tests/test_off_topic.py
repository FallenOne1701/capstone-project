"""Advice and off-topic (banking, loans, cards…) questions are never answered (Plan 3b Task 1b)."""

import asyncio

import pytest

from app import deps
from app.desk.templates import ADVICE_REFUSAL, OUT_OF_SCOPE_REPLY, PERFORMANCE_REFUSAL
from app.intent.classifier import classify_intent
from app.models import Draft, Ticket
from tests.conftest_corpus import build_fixture_retriever


@pytest.fixture(scope="module")
def fixture_retriever(tmp_path_factory):
    return build_fixture_retriever(tmp_path_factory.mktemp("off"))


@pytest.fixture()
def wired(client, monkeypatch, fixture_retriever):
    monkeypatch.setattr(deps, "get_retriever", lambda: fixture_retriever)
    return client


def _draft(client, db, text):
    r = client.post("/api/ask", json={"text": text})
    assert r.status_code == 200, r.text
    t = db.query(Ticket).filter_by(code=r.json()["code"]).one()
    return r.json(), db.query(Draft).filter_by(ticket_id=t.id).one()


@pytest.mark.parametrize("q", [
    "Which bank gives the best FD rate?",
    "Should I take a personal loan from HDFC Bank?",
    "Is it a good idea to open a savings account in HDFC Bank or SBI?",
    "Which credit card should I get?",
    "Where should I invest 1 lakh?",
    "Is HDFC Mid Cap worth it?",
    "Recommend a good tax saving plan",
    "What is the best fund for me?",
    "Should I buy bitcoin or stocks?",
])
def test_advice_or_off_topic_never_answered(wired, db_session, q):
    _, d = _draft(wired, db_session, q)
    assert d.disposition == "refuse", (q, d.disposition, d.reply)
    assert d.reply in (ADVICE_REFUSAL, PERFORMANCE_REFUSAL, OUT_OF_SCOPE_REPLY)
    assert d.citation is None


@pytest.mark.parametrize("q", ["Which bank gives the best FD rate?", "How do I apply for a home loan?",
                               "What is the interest rate on a savings account?", "Which credit card should I get?"])
def test_banking_questions_are_off_topic(q):
    assert asyncio.run(classify_intent(q)).intent == "out_of_scope"


def test_off_topic_gets_immediate_notice(wired, db_session):
    body, d = _draft(wired, db_session, "Which bank gives the best FD rate?")
    assert body["notice"] == OUT_OF_SCOPE_REPLY
    assert d.reply == OUT_OF_SCOPE_REPLY


@pytest.mark.parametrize("q", ["What is the exit load of HDFC Mid Cap?", "What is the expense ratio of HDFC Small Cap Fund?",
                               "What is the minimum SIP for HDFC ELSS Tax Saver Fund?"])
def test_fund_fact_questions_still_answered(wired, db_session, q):
    _, d = _draft(wired, db_session, q)
    assert d.disposition == "reply", (q, d.reply)


def test_named_fund_question_is_never_off_topic_even_without_llm():
    # USE_LLM=0 in tests: the classifier can't ask the LLM, but a named HDFC fund keeps it in scope
    r = asyncio.run(classify_intent("When was HDFC Mid Cap Fund launched?"))
    assert r.intent == "fund_fact"
