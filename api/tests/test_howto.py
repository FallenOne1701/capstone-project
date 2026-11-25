"""How-to questions are answered from official Groww Help pages, in the page's own words (2026-11-25)."""

import asyncio
import json

import pytest

from app.corpus import reference
from app.corpus.howto import howto_fact, howto_topic
from app.guard.scope import sentence_count
from app.tickets.service import create_ticket, process_ticket
from tests.conftest_corpus import build_fixture_retriever

START = "https://groww.in/help/mutual-funds/mf-sip/how-to-start-a-sip-on-groww"
CHARGE = "https://groww.in/help/mutual-funds/sip/will-i-be-charged-for-cancelling-my-sip--37"
DOCS = {
    "sip_start": (START, "To start a SIP on Groww: - From the Home screen, go to the 'Mutual Funds' section. - Click on "
                         "'Explore' at the top. - Click on 'Start SIP.' - Enter the amount. - Pay via UPI or Netbanking. "
                         "Note: - The SIP can only be set up on a monthly basis. Was the answer helpful? CONTACT US"),
    "sip_cancel_charge": (CHARGE, "Customer Support Help and Support En हि Will I be charged for cancelling my SIP? "
                                  "No, you will not be charged for cancelling an SIP Was the answer helpful?"),
    "redeem_not_credited": ("https://groww.in/help/mutual-funds/order/redeem-is-completed-but-amount-has-not-been-credited-6",
                            "My redemption has been completed but the amount has not been credited. Why? The timing for "
                            "receiving your redemption amount depends on the mutual fund scheme's settlement cycle. "
                            "Equity Funds: T+3 business days."),
    "redeem_nav": ("https://groww.in/help/mutual-funds/order/when-withdrawing-redeeming-which-days-nav-will-be-applicable-1",
                   "Customer Support Help and Support En हि When withdrawing/redeeming which day's NAV will be applicable? "
                   "The cut-off time for all redemptions is 3 pm. Redeem before 3 pm - current day's NAV Redeem after 3 pm - "
                   "next day's NAV Was the answer helpful? CONTACT US"),
}


@pytest.fixture()
def pages(tmp_path, monkeypatch):
    monkeypatch.setattr(reference, "_dir", lambda: tmp_path)
    for topic, (url, text) in DOCS.items():
        (tmp_path / f"{topic}.json").write_text(json.dumps(
            {"topic": topic, "url": url, "title": topic, "text": text, "fetched_at": "2026-11-25"}, ensure_ascii=False),
            encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("q, topic", [
    ("How do I start a SIP in HDFC Mid Cap Fund on Groww?", "sip_start"),
    ("how to set up a sip", "sip_start"),
    ("How do I cancel a SIP?", "sip_cancel"),
    ("how to stop my sip", "sip_cancel"),
    ("Will I be charged for cancelling my SIP?", "sip_cancel_charge"),
    ("Can I cancel my SIP anytime?", "sip_cancel_anytime"),
    ("How can I change my SIP date?", "sip_change"),
    ("SIP amount got deducted even after I cancelled", "sip_deducted_after_cancel"),
    ("I placed an order by mistake, can I cancel it?", "order_cancel"),
    ("How can I redeem my units of HDFC Small Cap Fund?", "redeem_how"),
    ("Can I withdraw my mutual fund money any time?", "redeem_anytime"),
    ("Is there a limit on how much I can redeem?", "redeem_limit"),
    ("Which day's NAV applies when I redeem?", "redeem_nav"),
    ("How long does it take to get my redeemed money?", "redeem_time"),
    ("My redemption is complete but money not credited", "redeem_not_credited"),
])
def test_how_to_questions_find_their_page(q, topic):
    assert howto_topic(q) == topic


@pytest.mark.parametrize("q", [
    "How do I download my capital gains statement?",   # no page covers it: stays not covered
    "What is exit load?",
    "my money is stuck since 3 days after i sold, what is happening",
    "Can I buy bitcoin on Groww?",
    "What is the minimum SIP amount for HDFC Small Cap Fund?",   # a fund fact, not a how-to
])
def test_other_questions_match_no_page(q):
    assert howto_topic(q) is None


def test_fact_is_the_pages_own_words_without_page_chrome(pages):
    fact, url, _ = howto_fact("sip_cancel_charge")
    assert url == CHARGE and fact == "No, you will not be charged for cancelling an SIP"
    fact, _, _ = howto_fact("redeem_nav")
    assert fact.startswith("The cut-off time for all redemptions is 3 pm.") and "helpful" not in fact
    assert "Customer Support" not in fact


def test_fact_keeps_the_steps_and_fits_the_reply_cap(pages):
    fact, url, _ = howto_fact("sip_start")
    assert url == START and "Start SIP" in fact and "Was the answer" not in fact
    assert sentence_count(fact) <= 2


def test_missing_page_gives_no_fact(pages):
    assert howto_fact("sip_cancel") is None


@pytest.fixture(scope="module")
def retriever(tmp_path_factory):
    return build_fixture_retriever(tmp_path_factory.mktemp("ht"))


def _ask(db, text, retriever):
    t, _ = asyncio.run(create_ticket(db, text))
    return asyncio.run(process_ticket(db, t.id, retriever=retriever))


def test_how_to_ticket_is_answered_from_the_help_page(db_session, pages, retriever):
    d = _ask(db_session, "How do I start a SIP in HDFC Mid Cap Fund on Groww?", retriever)
    assert d.citation == START and d.review_status == "pass" and d.disposition == "reply"
    assert "Start SIP" in d.reply and START in d.reply and "Last checked: 2026-11-25" in d.reply
    assert sentence_count(d.reply) <= 3
    assert "how-to" in d.routing_why.lower() and d.searched == ["howto:sip_start"]


def test_uncovered_how_to_still_says_not_covered(db_session, pages, retriever):
    d = _ask(db_session, "How do I download my capital gains statement?", retriever)
    assert d.citation is None or d.citation != START
    assert "don't cover" in d.reply


def test_advice_is_never_answered_from_a_help_page(db_session, pages, retriever):
    d = _ask(db_session, "Should I stop my SIP in HDFC Small Cap Fund now?", retriever)
    assert START not in (d.reply or "") and d.citation != CHARGE


def test_refresh_fetches_how_to_pages_as_their_own_kind(db_session, tmp_path, monkeypatch):
    from app.models import Source
    monkeypatch.setattr(reference, "_dir", lambda: tmp_path)
    page = "<html><body><article><p>To start a SIP on Groww, open the Mutual Funds section and tap Start SIP. " \
           "Enter the amount and pay via UPI or Netbanking.</p></article></body></html>"
    monkeypatch.setattr(reference, "_download", lambda url: page)
    reference.refresh_references(db_session, fetch=True)
    rows = db_session.query(Source).filter_by(kind="howto").all()
    assert len(rows) == len(reference.howtos()) >= 13 and all(r.status == "ok" for r in rows)
    assert (tmp_path / "sip_start.json").exists() and howto_fact("sip_start")[1] == START
    assert db_session.query(Source).filter_by(kind="reference").count() == len(reference.references())


def test_every_how_to_page_is_an_allowed_official_url():
    from app.config import is_allowed_source_url
    assert all(is_allowed_source_url(h["url"]) and h["url"].startswith("https://groww.in/help/") for h in reference.howtos())
    assert {h["topic"] for h in reference.howtos()} == {t for t, _ in __import__("app.corpus.howto", fromlist=["_RULES"])._RULES}


def test_a_title_question_at_the_top_is_not_part_of_the_answer(pages):
    fact, _, _ = howto_fact("redeem_not_credited")
    assert fact.startswith("The timing for receiving your redemption amount") and "Why?" not in fact
