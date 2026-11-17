import pytest

from app.guard.pii import find_pii, redact


@pytest.mark.parametrize("raw,ptype,token", [
    ("my pan is ABCDE1234F", "PAN", "[PAN]"),
    ("my pan is abcde1234f", "PAN", "[PAN]"),
    ("pan A B C D E 1 2 3 4 F please", "PAN", "[PAN]"),
    ("my pan is abcde 1234 f", "PAN", "[PAN]"),
    ("call me on 9876543210", "PHONE", "[PHONE]"),
    ("call +91 98765 43210 today", "PHONE", "[PHONE]"),
    ("phone 98765-43210", "PHONE", "[PHONE]"),
    ("aadhaar 1234 5678 9012", "AADHAAR", "[AADHAAR]"),
    ("account no 50100234567890", "ACCOUNT", "[ACCOUNT]"),
    ("account 5010 0234 5678 90", "ACCOUNT", "[ACCOUNT]"),
    ("a/c: 123456789", "ACCOUNT", "[ACCOUNT]"),
    ("my number is 501002345678901", "ACCOUNT", "[ACCOUNT]"),
    ("ifsc HDFC0001234", "IFSC", "[IFSC]"),
    ("mail me at ravi.k@example.com", "EMAIL", "[EMAIL]"),
    ("upi ravi@okhdfcbank", "UPI", "[UPI]"),
    ("OTP is 482913", "OTP", "[OTP]"),
    ("card 4111 1111 1111 1111", "CARD", "[CARD]"),
])
def test_redacts_each_type(raw, ptype, token):
    r = redact(raw)
    assert ptype in r.pii_types
    assert token in r.text
    for ch in ("1234", "98765", "ravi", "482913", "5010"):
        if ch in raw:
            assert ch not in r.text


@pytest.mark.parametrize("clean", [
    "What is the exit load of HDFC Mid Cap Fund?",
    "Exit load of 1% if redeemed within 1 year.",
    "The minimum SIP amount is ₹100.",
    "The expense ratio is 0.74%.",
    "AUM is ₹83,105 Cr as of 31 Oct 2026.",
    "Benchmark: NIFTY Midcap 150 Total Return Index",
    "Lock-in of 3 years for ELSS.",
    "Minimum SIP is 1000 a month.",
    "Last checked: 2026-11-17.",
    "Ticket GRW-AB12CD is in review.",
    "# Pulse — week ending 2026-11-17\n4 Play Store reviews",
    "1. Fees — 12 reviews\n2. Support — 9 reviews\n3. App — 7 reviews",
])
def test_leaves_clean_text_untouched(clean):
    r = redact(clean)
    assert r.text == clean
    assert r.pii_types == []


def test_multiple_types_and_order_stable():
    r = redact("PAN ABCDE1234F, phone 9876543210, acct 123456789012345")
    assert set(r.pii_types) == {"PAN", "PHONE", "ACCOUNT"}
    assert "ABCDE" not in r.text and "98765" not in r.text and "123456789012345" not in r.text


def test_find_pii_matches_redact():
    assert find_pii("ABCDE1234F") == ["PAN"]
    assert find_pii("nothing here") == []


def test_redact_is_idempotent():
    once = redact("pan ABCDE1234F phone 9876543210").text
    assert redact(once).text == once
    assert redact(once).pii_types == []
