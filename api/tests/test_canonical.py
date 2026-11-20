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


CHARGES = "https://groww.in/help/payments-&-withdrawals/payments-charges/what-fees-does-groww-charge--58"
REDEEM = "https://groww.in/help/mutual-funds/order/what-are-the-charges-applicable-for-redeeming--53"


@pytest.fixture()
def brokerage(db_session):
    ex = Explainer(topic="brokerage", title="Brokerage & charges", status="canonical", last_checked="2026-11-20", evidence={},
                   bullets=[{"text": "Groww charges a brokerage fee for executing your trades.", "url": CHARGES},
                            {"text": "Here's a breakdown: Equity Trading: The fee is either ₹20 or 0.1% of your trade value, whichever is lower.", "url": CHARGES},
                            {"text": "The minimum charge is ₹5.", "url": CHARGES},
                            {"text": "Groww charges ZERO fees for redeeming.", "url": REDEEM}])
    db_session.add(ex); db_session.commit()
    return ex


def test_amount_question_gets_the_figure_line(db_session, brokerage, retriever):
    from app.guard.scope import sentence_count
    d = ask(db_session, "What brokerage does Groww charge?", retriever)
    assert d.reused_explainer_id == brokerage.id and d.citation == CHARGES and d.review_status == "pass"
    assert "₹20 or 0.1%" in d.reply and "brokerage fee for executing" in d.reply
    assert sentence_count(d.reply) <= 3


def test_any_wording_without_a_definition_gets_the_figure(db_session, brokerage, retriever):
    d = ask(db_session, "Brokerage on Groww for equity delivery?", retriever)
    assert d.reused_explainer_id == brokerage.id and "₹20 or 0.1%" in d.reply


def test_definition_question_keeps_the_concept_line_only(db_session, brokerage, retriever):
    d = ask(db_session, "What is brokerage?", retriever)
    assert d.reused_explainer_id == brokerage.id and "₹" not in d.reply


def test_figure_line_never_borrowed_from_another_page(db_session, retriever):
    ex = Explainer(topic="brokerage", title="Brokerage", status="canonical", last_checked="2026-11-20", evidence={},
                   bullets=[{"text": "Groww charges a brokerage fee for executing your trades.", "url": CHARGES},
                            {"text": "Stamp duty of 0.015% applies on purchases.", "url": REDEEM}])
    db_session.add(ex); db_session.commit()
    d = ask(db_session, "What brokerage does Groww charge?", retriever)
    assert d.reused_explainer_id == ex.id and "0.015%" not in d.reply


def test_meaning_question_keeps_the_concept_line_only(db_session, brokerage, retriever):
    d = ask(db_session, "what does brokerage mean", retriever)
    assert d.reused_explainer_id == brokerage.id and "₹" not in d.reply
