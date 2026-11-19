import asyncio

import pytest

from app.intent.classifier import classify_intent, detect_language


def run(text):
    return asyncio.run(classify_intent(text))


@pytest.mark.parametrize("text,intent", [
    ("What is the exit load of HDFC Mid Cap?", "fee_question"),
    ("expense ratio of hdfc small cap fund", "fee_question"),
    ("mid cap ka exit load kitna hai", "fee_question"),
    ("What is the minimum SIP for HDFC ELSS?", "fund_fact"),
    ("benchmark of hdfc gilt fund", "fund_fact"),
    ("How do I redeem my units?", "how_to_process"),
    ("How do I buy HDFC Mid Cap on Groww?", "how_to_process"),
    ("How to sell my mutual fund units", "how_to_process"),
    ("sip kaise start kare", "how_to_process"),
    ("Should I buy HDFC Defence Fund?", "advice_request"),
    ("is mid cap fund good to invest now", "advice_request"),
    ("should I redeem because exit load is high", "advice_request"),
    ("kya mujhe small cap lena chahiye", "advice_request"),
    ("What returns did HDFC Mid Cap give last year?", "performance_request"),
    ("3 year CAGR of large cap fund", "performance_request"),
    ("kitna return milega", "performance_request"),
    ("My SIP amount was debited but units not credited", "account_issue"),
    ("my redemption money is stuck", "account_issue"),
    ("What is the weather today?", "out_of_scope"),
    ("🙂🙂", "out_of_scope"),
])
def test_rule_intents(text, intent):
    assert run(text).intent == intent


def test_scheme_and_fact_extracted():
    r = run("What is the exit load of HDFC Mid Cap?")
    assert r.scheme_ids == ["hdfc-mid-cap-fund-direct-growth"] and r.fact_key == "exit_load"


@pytest.mark.parametrize("text,lang", [
    ("What is the exit load?", "en"),
    ("mid cap ka exit load kitna hai", "hinglish"),
    ("एग्जिट लोड क्या है", "hi"),
])
def test_language(text, lang):
    assert detect_language(text) == lang


def test_devanagari_without_llm_is_out_of_scope_not_crash():
    assert run("एग्जिट लोड क्या है").intent in {"out_of_scope", "fee_question"}


# Eval run 1 (n05): a how-to-shaped question about a non-mutual-fund product is out of scope
@pytest.mark.parametrize("q", ["Can I buy bitcoin on Groww?", "How do I buy shares of Reliance on Groww?",
                               "How do I apply for a credit card on Groww?"])
def test_howto_about_other_products_is_out_of_scope(q):
    r = asyncio.run(classify_intent(q))
    assert r.intent == "out_of_scope"


@pytest.mark.parametrize("q", ["How do I redeem my mutual fund units to my bank account?",
                               "How do I start a SIP in HDFC Mid Cap Fund?"])
def test_mutual_fund_howtos_stay_howto(q):
    assert asyncio.run(classify_intent(q)).intent == "how_to_process"


# eval run 5 (adv2, adv3): advice phrasings the rules missed, so the AI sometimes got them wrong
@pytest.mark.parametrize("q", ["Which HDFC fund is best for me to invest 10 lakh in?",
                               "Bhai HDFC Mid Cap mein paisa lagau ya nahi? Batao",
                               "HDFC Small Cap mein paise daalu kya?",
                               "Is HDFC Gilt Fund the best for me?"])
def test_more_advice_phrasings_are_rules(q, monkeypatch):
    from app.intent import classifier

    async def no_ai(*a, **k):
        raise AssertionError("the AI should not be needed")
    monkeypatch.setattr(classifier, "complete_json", no_ai)
    assert asyncio.run(classify_intent(q)).intent == "advice_request"
