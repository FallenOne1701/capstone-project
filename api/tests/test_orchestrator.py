import asyncio
from datetime import date

import pytest

from app.desk.orchestrator import run_desk
from app.desk.templates import ACCOUNT_REPLY, ADVICE_REFUSAL, OUT_OF_SCOPE_REPLY, PERFORMANCE_REFUSAL
from app.guard.scope import sentence_count
from app.intent.classifier import classify_intent
from tests.conftest_corpus import build_fixture_retriever


@pytest.fixture(scope="module")
def retriever(tmp_path_factory):
    return build_fixture_retriever(tmp_path_factory.mktemp("o"))


def desk(text, retriever):
    async def go():
        intent = await classify_intent(text)
        return await run_desk(text, [], intent, retriever=retriever, themes=[],
                              last_checked=lambda u: "2026-11-17", today=date(2026, 11, 17))
    return asyncio.run(go())


def test_covered_question_replies_with_citation(retriever):
    r = desk("What is the exit load of HDFC Mid Cap Fund?", retriever)
    assert r.draft.disposition == "reply" and r.review.status == "pass"
    assert r.draft.citation.endswith("hdfc-mid-cap-fund-direct-growth")
    assert "2026-11-17" in r.draft.reply and sentence_count(r.draft.reply) <= 3


@pytest.mark.parametrize("text,expected", [
    ("Should I buy HDFC Defence Fund?", ADVICE_REFUSAL),
    ("What returns did mid cap give?", PERFORMANCE_REFUSAL),
    ("my SIP was debited but units not credited", ACCOUNT_REPLY),
])
def test_template_dispositions(retriever, text, expected):
    r = desk(text, retriever)
    assert r.draft.reply == expected and r.review.status == "pass"


def test_not_covered_names_searched(retriever):
    # an in-scope fund question our sources don't cover (Plan 3b: off-topic questions are refused instead)
    r = desk("When was HDFC Mid Cap Fund launched?", retriever)
    assert r.draft.disposition == "handoff" and "Searched:" in r.draft.reply
    assert r.review.status == "pass"


def test_off_topic_question_is_refused(retriever):
    r = desk("Who is the CEO of Groww?", retriever)
    assert r.draft.disposition == "refuse" and r.draft.reply == OUT_OF_SCOPE_REPLY
    assert r.review.status == "pass"


def test_works_with_llm_disabled_and_no_themes(retriever):
    r = desk("minimum sip for hdfc elss", retriever)
    assert r.pattern.theme_id == "other" and r.draft.reply
