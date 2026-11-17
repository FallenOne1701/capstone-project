import asyncio

import pytest

from app.models import Explainer
from app.tickets.service import create_ticket, process_ticket
from tests.conftest_corpus import build_fixture_retriever

MID = "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth"
CONCEPT = "https://groww.in/help/mutual-funds/order/what-is-exit-load--71"


@pytest.fixture(scope="module")
def retriever(tmp_path_factory):
    return build_fixture_retriever(tmp_path_factory.mktemp("cn"))


@pytest.fixture()
def canonical(db_session):
    ex = Explainer(topic="exit_load", title="Exit load", status="canonical", last_checked="2026-11-17", evidence={},
                   bullets=[{"text": "Exit load is a fee payable to a mutual fund house for exiting a fund before a specified period.", "url": CONCEPT},
                            {"text": "Exit load for HDFC Mid Cap Fund Direct Growth: Exit load of 1% if redeemed within 1 year.", "url": MID}])
    db_session.add(ex); db_session.commit()
    return ex


def ask(db, text, retriever):
    t, _ = asyncio.run(create_ticket(db, text))
    return asyncio.run(process_ticket(db, t.id, retriever=retriever))


def test_concept_question_reuses_canonical(db_session, canonical, retriever):
    d = ask(db_session, "What is exit load?", retriever)
    assert d.reused_explainer_id == canonical.id and d.citation == CONCEPT and d.review_status == "pass"


def test_scheme_question_uses_scheme_bullet(db_session, canonical, retriever):
    d = ask(db_session, "exit load of HDFC Mid Cap?", retriever)
    assert d.reused_explainer_id == canonical.id and d.citation == MID


def test_scheme_not_in_explainer_falls_back_to_desk(db_session, canonical, retriever):
    d = ask(db_session, "exit load of HDFC Small Cap?", retriever)
    assert d.reused_explainer_id is None and d.citation.endswith("hdfc-small-cap-fund-direct-growth")


def test_no_canonical_uses_desk(db_session, retriever):
    d = ask(db_session, "What is exit load?", retriever)
    assert d.reused_explainer_id is None and d.disposition == "handoff"


def test_superseded_not_reused(db_session, canonical, retriever):
    canonical.status = "superseded"; db_session.commit()
    assert ask(db_session, "What is exit load?", retriever).reused_explainer_id is None


def test_non_fee_intent_never_reuses(db_session, canonical, retriever):
    assert ask(db_session, "Should I redeem because of exit load?", retriever).reused_explainer_id is None
