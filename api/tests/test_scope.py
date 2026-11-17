import pytest

from app.guard.scope import (
    bullet_count, check_output, detect_advice, detect_performance,
    sentence_count, strip_advice_and_performance, truncate_sentences, word_count,
)


@pytest.mark.parametrize("text", [
    "You should buy this fund now.",
    "We recommend switching to the large cap fund.",
    "Consider staying invested for the long term.",
    "It is a good time to sell.",
    "Hold your units.",
])
def test_advice_detected(text):
    assert detect_advice(text)


@pytest.mark.parametrize("text", [
    "Exit load of 1% if redeemed within 1 year.",
    "Redemption proceeds are credited to your bank account.",
    "The minimum SIP amount is ₹100.",
    "Fund holdings are listed on the scheme page.",
])
def test_advice_not_flagged_for_facts(text):
    assert not detect_advice(text)


@pytest.mark.parametrize("text", [
    "The fund gave 24% returns last year.",
    "3-year CAGR is 21.4%.",
    "It returned 18% in 2025.",
    "Performance has been strong.",
    "Expected returns are high.",
])
def test_performance_detected(text):
    assert detect_performance(text)


@pytest.mark.parametrize("text", [
    "The fund benchmark is NIFTY Midcap 150 Total Return Index.",
    "Benchmark: NIFTY 100 TRI.",
    "The expense ratio is 0.74%.",
    "Exit load of 1% if redeemed within 1 year.",
    "Stamp duty of 0.005% applies on purchases.",
])
def test_performance_not_flagged_for_fee_facts(text):
    assert not detect_performance(text)


def test_counts():
    assert sentence_count("One. Two! Three? Four.") == 4
    assert sentence_count("Source: https://groww.in/mutual-funds/x. Last checked: 2026-11-17.") == 2
    assert word_count("a b  c\nd") == 4
    assert bullet_count("- a\n- b\n* c\n1. d\ntext") == 4


def test_check_output_caps():
    assert [v.check for v in check_output("A. B. C. D.", kind="reply")] == ["shape"]
    assert check_output("A. B. C.", kind="reply") == []
    assert [v.check for v in check_output(" ".join(["w"] * 251), kind="pulse")] == ["shape"]
    assert [v.check for v in check_output("\n".join(["- x"] * 7), kind="explainer")] == ["shape"]


def test_check_output_flags_pii_and_advice():
    checks = {v.check for v in check_output("You should buy. Call 9876543210.", kind="reply")}
    assert {"advice", "pii"} <= checks


def test_strip_and_truncate():
    cleaned = strip_advice_and_performance("Exit load is 1%. You should buy now. It gave 20% returns.")
    assert not detect_advice(cleaned) and not detect_performance(cleaned)
    assert "Exit load is 1%." in cleaned
    assert truncate_sentences("A. B. C. D.", 3) == "A. B. C."
