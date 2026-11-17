from datetime import date

import pytest

from app.desk.compliance import run_compliance
from app.desk.contracts import DateWindow, ThemeStat
from app.desk.facts import run_facts
from app.desk.pattern import run_pattern
from app.intent.classifier import IntentResult
from tests.conftest_corpus import build_fixture_retriever


@pytest.fixture(scope="module")
def retriever(tmp_path_factory):
    return build_fixture_retriever(tmp_path_factory.mktemp("c"))


def test_facts_covered(retriever):
    f = run_facts("exit load of hdfc mid cap fund", retriever, lambda url: "2026-11-17")
    assert f.status == "covered" and f.last_checked == "2026-11-17"
    assert f.citation.endswith("hdfc-mid-cap-fund-direct-growth")


def test_facts_not_covered_names_search(retriever):
    f = run_facts("who is the CEO of Groww", retriever, lambda url: None)
    assert f.status == "not_covered" and f.searched


def _theme(**kw):
    w = DateWindow(start="2026-09-22", end="2026-11-16")
    r = DateWindow(start="2026-11-10", end="2026-11-16")
    base = dict(theme_id="fees_charges", name="Fees & charges", team="Fees and mutual fund ops",
                cues=["exit load", "charges", "fee"], count=60, recent_count=30, window=w, recent_window=r)
    base.update(kw)
    return ThemeStat(**base)


def test_pattern_matches_cues_and_rising():
    p = run_pattern("why was exit load charged", [_theme()], today=date(2026, 11, 17))
    assert p.theme_id == "fees_charges" and p.signal == "rising" and p.count == 60


def test_pattern_no_themes_is_other_one_off():
    p = run_pattern("anything", [], today=date(2026, 11, 17))
    assert p.theme_id == "other" and p.signal == "one-off" and p.count == 0
    assert p.window.end == "2026-11-17"


def _intent(name):
    return IntentResult(intent=name, scheme_ids=[], fact_key=None, language="en", confidence="rule")


def test_compliance_uses_intent_not_verbs():
    c = run_compliance("How do I redeem my units?", [], _intent("how_to_process"))
    assert c.flags == [] and not c.advice_refusal
    c2 = run_compliance("should I buy", [], _intent("advice_request"))
    assert "advice" in c2.flags and c2.advice_refusal


def test_compliance_flags_residual_pii():
    c = run_compliance("call 9876543210", [], _intent("account_issue"))
    assert "pii" in c.flags and "PHONE" in c.pii_types
